"""Send drift events and acknowledge only authenticated SES delivery receipts.

One worker and durable SQLite journal per environment. No HTTP listener is needed.
SES accepting a send is deliberately NOT treated as delivery.
"""

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

LOG = logging.getLogger("alert_delivery")
TERMINAL_FAILURES = {"Bounce", "Complaint", "Reject", "Rendering Failure"}


@dataclass(frozen=True)
class Settings:
    catalog: str
    sender: str
    recipient: str
    account_id: str
    region: str
    configuration_set: str
    queue_url: str
    databricks_host: str
    database: Path
    poll_seconds: int = 600
    retry_seconds: int = 3600

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.catalog):
            raise ValueError("PM_CATALOG must be a simple catalog identifier")
        for address in (self.sender, self.recipient):
            if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", address):
                raise ValueError("Configure one plain sender and one recipient email address")
        if not re.fullmatch(r"\d{12}", self.account_id):
            raise ValueError("AWS_ACCOUNT_ID must contain 12 digits")
        prefix = f"https://sqs.{self.region}.amazonaws.com/{self.account_id}/"
        if not self.queue_url.startswith(prefix) or not self.queue_url[len(prefix):]:
            raise ValueError("Receipt queue must belong to the configured AWS account and region")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.configuration_set):
            raise ValueError("Invalid SES configuration set name")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.databricks_host):
            raise ValueError("DATABRICKS_SERVER_HOSTNAME must be a hostname without a scheme or path")
        if self.poll_seconds < 10 or self.retry_seconds < self.poll_seconds:
            raise ValueError("Poll must be >=10 seconds and retry must be >= poll")

    @property
    def events_table(self):
        return f"{self.catalog}.gold_data.prediction_monitoring_drift_alert_events"

    @property
    def state_table(self):
        return f"{self.catalog}.gold_data.prediction_monitoring_drift_alert_state"

    @property
    def scope(self):
        # Prevent accidental reuse of DEV delivery evidence for production.
        return json.dumps([self.catalog, self.sender, self.recipient, self.account_id,
                           self.region, self.configuration_set, self.queue_url, self.databricks_host])

    @classmethod
    def from_env(cls):
        return cls(
            catalog=os.environ["PM_CATALOG"], sender=os.environ["ALERT_SENDER"],
            recipient=os.environ["ALERT_RECIPIENT"], account_id=os.environ["AWS_ACCOUNT_ID"],
            region=os.environ["AWS_REGION"], configuration_set=os.environ["SES_CONFIGURATION_SET"],
            queue_url=os.environ["RECEIPT_QUEUE_URL"],
            databricks_host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            database=Path(os.environ["PM_DELIVERY_DB"]),
            poll_seconds=int(os.getenv("POLL_SECONDS", "600")),
            retry_seconds=int(os.getenv("RETRY_SECONDS", "3600")),
        )


class Journal:
    """Commit send attempts before sending; commit receipts before deleting SQS messages."""

    def __init__(self, path, scope):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, events TEXT NOT NULL, created_at REAL NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS batch_events (
                event_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, created_at REAL NOT NULL,
                status TEXT NOT NULL, provider_id TEXT, delivered_at TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS receipts (
                digest TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, event_type TEXT NOT NULL,
                provider_id TEXT NOT NULL, received_at REAL NOT NULL, payload TEXT NOT NULL);
        """)
        previous = self.db.execute("SELECT value FROM metadata WHERE key='scope'").fetchone()
        if previous and previous[0] != scope:
            self.db.close()
            raise ValueError("Journal belongs to a different environment or recipient")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('scope', ?)", (scope,))

    def known(self, event_id):
        return self.db.execute("SELECT 1 FROM batch_events WHERE event_id=?", (event_id,)).fetchone() is not None

    def enqueue(self, events, now):
        batch_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO batches(id,events,created_at) VALUES (?,?,?)",
                            (batch_id, json.dumps(events, default=str), now))
            self.db.executemany("INSERT INTO batch_events VALUES (?,?)",
                                [(event["event_id"], batch_id) for event in events])
        return batch_id

    def outstanding(self):
        return self.db.execute("SELECT * FROM batches WHERE acknowledged=0 ORDER BY created_at,id").fetchall()

    def delivered(self, batch_id):
        return self.db.execute(
            "SELECT * FROM attempts WHERE batch_id=? AND status='Delivery' ORDER BY delivered_at LIMIT 1",
            (batch_id,),
        ).fetchone()

    def prepare_attempt(self, batch_id, now, retry_seconds):
        if self.delivered(batch_id):
            return None
        latest = self.db.execute(
            "SELECT * FROM attempts WHERE batch_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
            (batch_id,),
        ).fetchone()
        if latest and latest["status"] in TERMINAL_FAILURES:
            LOG.error("Delivery blocked for batch %s: %s; inspect --status", batch_id, latest["status"])
            return None
        if latest and latest["status"] != "RETRY_ALLOWED" and now - latest["created_at"] < retry_seconds:
            return None
        attempt_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO attempts(id,batch_id,created_at,status) VALUES (?,?,?,'WAITING')",
                            (attempt_id, batch_id, now))
        return attempt_id

    def sent(self, attempt_id, provider_id):
        with self.db:
            self.db.execute("UPDATE attempts SET provider_id=? WHERE id=?", (provider_id, attempt_id))

    def send_error(self, attempt_id, error):
        # A timeout can occur after SES accepted the message. Its receipt can still
        # correlate through the precommitted attempt tag even without a message ID.
        with self.db:
            self.db.execute("UPDATE attempts SET status='SEND_ERROR',error=? WHERE id=?", (error, attempt_id))

    def record_receipt(self, receipt, settings, now):
        mail = receipt["mail"]
        tags = mail.get("tags", {})
        attempt_ids = tags.get("pm_attempt_id", [])
        if len(attempt_ids) != 1:
            raise ValueError("Receipt lacks an unambiguous attempt ID")
        attempt = self.db.execute("SELECT * FROM attempts WHERE id=?", (attempt_ids[0],)).fetchone()
        if not attempt:
            raise ValueError("Unknown attempt; retain receipt for investigation")
        if (mail.get("sendingAccountId") != settings.account_id
                or mail.get("source", "").lower() != settings.sender.lower()
                or tags.get("pm_batch_id") != [attempt["batch_id"]]
                or tags.get("ses:configuration-set") != [settings.configuration_set]
                or mail.get("destination") != [settings.recipient]):
            raise ValueError("Receipt source, configuration set, batch or recipient mismatch")
        provider_id = mail["messageId"]
        if not provider_id or (attempt["provider_id"] and attempt["provider_id"] != provider_id):
            raise ValueError("Receipt message ID mismatch")
        kind = receipt["eventType"]
        if kind not in TERMINAL_FAILURES | {"Delivery", "Send", "DeliveryDelay"}:
            raise ValueError("Unsupported receipt type")
        delivered_at = None
        if kind == "Delivery":
            delivery = receipt["delivery"]
            if settings.recipient not in delivery.get("recipients", []):
                raise ValueError("Delivery receipt does not confirm the intended recipient")
            timestamp = datetime.fromisoformat(delivery["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Delivery timestamp must include a timezone")
            delivered_at = timestamp.astimezone(timezone.utc).isoformat()
        raw = json.dumps(receipt, sort_keys=True)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?,?)",
                            (hashlib.sha256(raw.encode()).hexdigest(), attempt["id"], kind, provider_id, now, raw))
            if kind == "Delivery" or kind in TERMINAL_FAILURES:
                # Successful delivery is monotonic; a duplicate or late bounce
                # must not erase a confirmed receipt already used for acknowledgement.
                self.db.execute(
                    "UPDATE attempts SET status=?,provider_id=?,delivered_at=? WHERE id=? AND status!='Delivery'",
                    (kind, provider_id, delivered_at, attempt["id"]),
                )

    def acknowledged(self, batch_id):
        with self.db:
            self.db.execute("UPDATE batches SET acknowledged=1 WHERE id=?", (batch_id,))

    def retry_failed(self, batch_id):
        # Explicit operator action after correcting a rejected/bouncing address.
        # Never resets a successful delivery or changes Databricks notification state.
        with self.db:
            cursor = self.db.execute(
                "UPDATE attempts SET status='RETRY_ALLOWED' "
                "WHERE batch_id=? AND status IN ('Bounce','Complaint','Reject','Rendering Failure')",
                (batch_id,),
            )
            if not cursor.rowcount:
                raise ValueError("No terminal failure found for that batch")

    def status(self):
        return [dict(row) for row in self.db.execute(
            "SELECT b.id AS batch_id,b.acknowledged,a.id AS attempt_id,a.status,"
            "a.provider_id,a.delivered_at,a.error FROM batches b "
            "LEFT JOIN attempts a ON a.batch_id=b.id ORDER BY b.created_at,a.created_at"
        )]


class SqlEventStore:
    def __init__(self, connect, settings):
        self.connect = connect
        self.events_table = settings.events_table
        self.state_table = settings.state_table

    def pending(self):
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                f"SELECT event_id,feature,event_type,severity,psi,recommended_action,event_timestamp "
                f"FROM {self.events_table} WHERE notification_required=TRUE "
                "AND notification_status='PENDING' ORDER BY event_timestamp,event_id"
            )
            columns = [item[0] for item in cursor.description]
            while rows := cursor.fetchmany(100):
                for row in rows:
                    yield dict(zip(columns, row))

    def acknowledge(self, event_ids, delivered_at):
        if not event_ids or len(event_ids) > 50:
            raise ValueError("A delivery batch must contain 1 to 50 event IDs")
        placeholders = ",".join("?" for _ in event_ids)
        when = datetime.fromisoformat(delivered_at).astimezone(timezone.utc).replace(tzinfo=None)
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                f"UPDATE {self.events_table} SET notification_status='SENT' "
                f"WHERE event_id IN ({placeholders}) AND notification_required=TRUE "
                "AND notification_status='PENDING'", event_ids,
            )
            # Each statement is idempotent. If the second fails, the durable
            # receipt is retained and both statements are retried next cycle.
            cursor.execute(
                f"UPDATE {self.state_table} SET last_notified_at=CASE "
                "WHEN last_notified_at IS NULL OR last_notified_at < ? THEN ? "
                "ELSE last_notified_at END, last_updated_at=CURRENT_TIMESTAMP "
                f"WHERE feature IN (SELECT feature FROM {self.events_table} "
                f"WHERE event_id IN ({placeholders}) AND notification_required=TRUE "
                "AND notification_status='SENT')", [when, when, *event_ids],
            )


class Worker:
    def __init__(self, settings, journal, store, ses, sqs, clock=time.time):
        self.settings, self.journal, self.store = settings, journal, store
        self.ses, self.sqs, self.clock = ses, sqs, clock

    def tick(self):
        # Drain a bounded number of receipts before attempting more sends.
        for _ in range(10):
            messages = self.sqs.receive_message(
                QueueUrl=self.settings.queue_url, MaxNumberOfMessages=10,
                WaitTimeSeconds=0, VisibilityTimeout=120,
            ).get("Messages", [])
            if not messages:
                break
            for message in messages:
                try:
                    self.journal.record_receipt(json.loads(message["Body"]), self.settings, self.clock())
                except (ValueError, KeyError, TypeError) as exc:
                    LOG.error("Invalid receipt retained for dead-letter handling: %s", type(exc).__name__)
                    continue
                self.sqs.delete_message(QueueUrl=self.settings.queue_url, ReceiptHandle=message["ReceiptHandle"])

        for batch in self.journal.outstanding():
            receipt = self.journal.delivered(batch["id"])
            if receipt:
                self.store.acknowledge(
                    [event["event_id"] for event in json.loads(batch["events"])], receipt["delivered_at"],
                )
                self.journal.acknowledged(batch["id"])
                LOG.info("Acknowledged delivered batch %s", batch["id"])

        new_events = []
        count = 0
        for event in self.store.pending():
            if self.journal.known(event["event_id"]):
                continue
            new_events.append(event)
            count += 1
            if len(new_events) == 50:
                self.journal.enqueue(new_events, self.clock())
                new_events = []
            if count == 1000:
                break
        if new_events:
            self.journal.enqueue(new_events, self.clock())

        sends = 0
        for batch in self.journal.outstanding():
            attempt_id = self.journal.prepare_attempt(batch["id"], self.clock(), self.settings.retry_seconds)
            if attempt_id is None:
                continue
            events = json.loads(batch["events"])
            body = "Predictive maintenance drift events (including recoveries):\n\n" + "\n\n".join(
                f"Event: {event['event_id']}\nFeature: {event['feature']}\n"
                f"Transition: {event['event_type']} / {event['severity']}\n"
                f"PSI: {event['psi']}\nAction: {event['recommended_action']}"
                for event in events
            )
            try:
                response = self.ses.send_email(
                    FromEmailAddress=self.settings.sender,
                    Destination={"ToAddresses": [self.settings.recipient]},
                    Content={"Simple": {
                        "Subject": {"Data": f"Predictive maintenance: {len(events)} drift event(s)", "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                    }},
                    ConfigurationSetName=self.settings.configuration_set,
                    EmailTags=[{"Name": "pm_attempt_id", "Value": attempt_id},
                               {"Name": "pm_batch_id", "Value": batch["id"]}],
                )
                self.journal.sent(attempt_id, response["MessageId"])
                LOG.info("SES accepted batch %s; waiting for delivery receipt", batch["id"])
            except Exception as exc:
                self.journal.send_error(attempt_id, type(exc).__name__)
                LOG.error("Send unconfirmed for batch %s: %s", batch["id"], type(exc).__name__)
            sends += 1
            if sends == 20:
                break


def databricks_connection():
    from databricks import sql
    from databricks.sdk.core import Config, oauth_service_principal

    host = os.environ["DATABRICKS_SERVER_HOSTNAME"].removeprefix("https://").rstrip("/")
    # A dedicated M2M principal owns acknowledgement writes; do not give the
    # public dashboard's read-only principal MODIFY privileges.
    def credentials_provider():
        return oauth_service_principal(Config(
            host=f"https://{host}", client_id=os.environ["DATABRICKS_CLIENT_ID"],
            client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
        ))
    return sql.connect(
        server_hostname=host, http_path=os.environ["DATABRICKS_HTTP_PATH"],
        credentials_provider=credentials_provider,
        session_configuration={"spark.sql.session.timeZone": "UTC"},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Process one cycle; CAN send emails and acknowledge delivery")
    mode.add_argument("--status", action="store_true", help="Inspect the local receipt journal only")
    mode.add_argument("--retry-failed", metavar="BATCH_ID", help="Explicitly retry a terminal failure after fixing its cause")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.umask(0o077)
    settings = Settings.from_env()
    settings.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(str(settings.database) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal = Journal(settings.database, settings.scope)
        try:
            if args.status:
                print(json.dumps(journal.status(), indent=2))
                return
            if args.retry_failed:
                journal.retry_failed(args.retry_failed)
                return
            import boto3
            from botocore.config import Config as AwsConfig
            # SES SendEmail has no idempotency key. Avoid hidden SDK retries;
            # explicit attempts and receipt tags keep ambiguous sends traceable.
            aws_config = AwsConfig(connect_timeout=10, read_timeout=30, retries={"total_max_attempts": 1})
            session = boto3.Session(region_name=settings.region)
            worker = Worker(settings, journal, SqlEventStore(databricks_connection, settings),
                            session.client("sesv2", config=aws_config), session.client("sqs", config=aws_config))
            while True:
                try:
                    worker.tick()
                except Exception as exc:
                    LOG.error("Delivery cycle failed; pending events and receipts retained: %s", type(exc).__name__)
                    if args.once:
                        raise
                if args.once:
                    return
                time.sleep(settings.poll_seconds)
        finally:
            journal.db.close()


if __name__ == "__main__":
    main()
