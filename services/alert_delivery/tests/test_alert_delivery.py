"""Offline delivery failure/recovery tests using real SQL and a durable journal.

SES/SQS are simulated at the network boundary; no email, AWS or Databricks calls.
"""
from dataclasses import replace
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("alert_worker", ROOT / "services/alert_delivery/worker.py")
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)
sqlite3.register_adapter(datetime, lambda value: value.isoformat(sep=" "))


class Ses:
    def __init__(self):
        self.calls = []
        self.fail = False

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("Response lost after SES may have accepted it")
        return {"MessageId": f"ses-{len(self.calls)}"}


class Sqs:
    def __init__(self):
        self.messages = []
        self.deleted = []

    def receive_message(self, **kwargs):
        messages, self.messages = self.messages[:10], self.messages[10:]
        return {"Messages": messages}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs["ReceiptHandle"])

    def push(self, receipt, handle="receipt-1"):
        self.messages.append({"Body": json.dumps(receipt), "ReceiptHandle": handle})


@pytest.fixture
def env(tmp_path):
    settings = w.Settings(
        catalog="predictivemaintenance_dev", sender="alerts@example.com", recipient="operator@example.com",
        account_id="123456789012", region="us-east-1", configuration_set="pm-alerts-dev",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/receipts",
        databricks_host="dev.cloud.databricks.com", database=tmp_path / "journal.sqlite3",
    )
    events_db = tmp_path / "events.sqlite3"
    def connect():
        return sqlite3.connect(events_db, isolation_level=None)
    with connect() as db:
        db.executescript("""
            CREATE TABLE events (event_id TEXT PRIMARY KEY, feature TEXT, event_type TEXT,
                severity TEXT, psi REAL, recommended_action TEXT, event_timestamp TEXT,
                notification_required INTEGER DEFAULT 1, notification_status TEXT DEFAULT 'PENDING',
                monitoring_run_id TEXT DEFAULT 'same-run');
            CREATE TABLE state (feature TEXT PRIMARY KEY, last_notified_at TEXT, last_updated_at TEXT);
        """)
    journal = w.Journal(settings.database, settings.scope)
    store = w.SqlEventStore(connect, settings)
    # Same parameterized statements as production, against local SQL tables.
    store.events_table, store.state_table = "events", "state"
    ses, sqs, clock = Ses(), Sqs(), [100000.0]
    worker = w.Worker(settings, journal, store, ses, sqs, lambda: clock[0])
    result = {"settings": settings, "journal": journal, "store": store, "ses": ses,
              "sqs": sqs, "clock": clock, "worker": worker, "connect": connect}
    yield result
    journal.db.close()


def add_event(env, event_id="event-1", feature="Torque_Nm", kind="NEW_ALERT", psi=0.3):
    with env["connect"]() as db:
        db.execute("INSERT INTO events(event_id,feature,event_type,severity,psi,recommended_action,event_timestamp) "
                   "VALUES (?,?,?,?,?,?,?)", (event_id, feature, kind, "NORMAL" if psi < 0.1 else "HIGH",
                                             psi, "Investigate" if psi >= 0.1 else "Recovered", "2026-11-01 00:00:00"))
        db.execute("INSERT OR IGNORE INTO state(feature) VALUES (?)", (feature,))


def statuses(env):
    with env["connect"]() as db:
        return dict(db.execute("SELECT event_id,notification_status FROM events"))


def receipt(env, call_index=0, kind="Delivery"):
    sent = env["ses"].calls[call_index]
    tags = {tag["Name"]: [tag["Value"]] for tag in sent["EmailTags"]}
    tags["ses:configuration-set"] = [env["settings"].configuration_set]
    return {"eventType": kind, "mail": {
        "sendingAccountId": env["settings"].account_id, "source": env["settings"].sender,
        "destination": [env["settings"].recipient], "messageId": f"ses-{call_index + 1}", "tags": tags,
    }, "delivery": {"recipients": [env["settings"].recipient], "timestamp": "2026-11-19T20:00:00Z"}}


def test_send_acceptance_and_age_never_count_as_delivery(env):
    add_event(env)
    env["worker"].tick()
    assert statuses(env) == {"event-1": "PENDING"}
    env["sqs"].push(receipt(env, kind="Send"))
    env["clock"][0] += 7200
    env["worker"].tick()
    assert statuses(env) == {"event-1": "PENDING"}
    assert len(env["ses"].calls) == 2  # explicit retry, not silent retirement


def test_recovery_delivery_acknowledges_exact_frozen_event_ids(env):
    add_event(env, kind="RESOLVED", psi=0.02)
    env["worker"].tick()
    assert "RESOLVED" in env["ses"].calls[0]["Content"]["Simple"]["Body"]["Text"]["Data"]
    # Same monitoring run, but absent from the email already sent.
    add_event(env, "event-2", "Tool_wear_min")
    env["sqs"].push(receipt(env))
    env["worker"].tick()
    assert statuses(env) == {"event-1": "SENT", "event-2": "PENDING"}
    with env["connect"]() as db:
        state = dict(db.execute("SELECT feature,last_notified_at FROM state"))
    assert state["Torque_Nm"] == "2026-11-19 20:00:00"
    assert state["Tool_wear_min"] is None


def test_database_failure_retries_saved_receipt_after_restart(env, monkeypatch):
    add_event(env)
    env["worker"].tick()
    env["sqs"].push(receipt(env))
    acknowledge = env["store"].acknowledge
    def fail(*args):
        raise ConnectionError("Databricks unavailable")
    monkeypatch.setattr(env["store"], "acknowledge", fail)
    with pytest.raises(ConnectionError):
        env["worker"].tick()
    assert env["sqs"].deleted == ["receipt-1"]  # durable journal now owns the receipt
    assert statuses(env)["event-1"] == "PENDING"
    env["journal"].db.close()
    journal = w.Journal(env["settings"].database, env["settings"].scope)
    monkeypatch.setattr(env["store"], "acknowledge", acknowledge)
    restarted = w.Worker(env["settings"], journal, env["store"], env["ses"], env["sqs"], lambda: env["clock"][0])
    try:
        restarted.tick()
        assert statuses(env)["event-1"] == "SENT"
        assert len(env["ses"].calls) == 1
    finally:
        journal.db.close()


def test_duplicate_receipts_are_idempotent(env):
    add_event(env)
    env["worker"].tick()
    event = receipt(env)
    env["sqs"].push(event, "one")
    env["sqs"].push(event, "two")
    env["worker"].tick()
    env["worker"].tick()
    assert statuses(env)["event-1"] == "SENT"
    assert env["journal"].db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1
    assert len(env["ses"].calls) == 1


def test_partial_database_acknowledgement_is_retried(env, monkeypatch):
    add_event(env)
    env["worker"].tick()
    env["sqs"].push(receipt(env))
    original_connect = env["store"].connect
    fail_once = [True]
    class Cursor:
        def __init__(self, inner): self.inner = inner
        def __getattr__(self, name): return getattr(self.inner, name)
        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE state") and fail_once[0]:
                fail_once[0] = False
                raise ConnectionError("State update failed after event update committed")
            return self.inner.execute(sql, parameters)
    class Connection:
        def __init__(self): self.inner = original_connect()
        def cursor(self): return Cursor(self.inner.cursor())
        def close(self): self.inner.close()
    monkeypatch.setattr(env["store"], "connect", Connection)
    with pytest.raises(ConnectionError):
        env["worker"].tick()
    assert statuses(env)["event-1"] == "SENT"
    assert env["journal"].outstanding()
    env["worker"].tick()
    assert not env["journal"].outstanding()
    with original_connect() as db:
        assert db.execute("SELECT last_notified_at FROM state").fetchone()[0] == "2026-11-19 20:00:00"
    assert len(env["ses"].calls) == 1


def test_ambiguous_send_response_is_recovered_by_precommitted_tag(env):
    add_event(env)
    env["ses"].fail = True
    env["worker"].tick()
    assert env["journal"].status()[0]["provider_id"] is None
    assert statuses(env)["event-1"] == "PENDING"
    env["sqs"].push(receipt(env))
    env["worker"].tick()
    assert statuses(env)["event-1"] == "SENT"


@pytest.mark.parametrize("kind", ["Bounce", "Complaint", "Reject", "Rendering Failure"])
def test_failed_delivery_stays_pending_and_requires_explicit_retry(env, kind):
    add_event(env)
    env["worker"].tick()
    env["sqs"].push(receipt(env, kind=kind))
    env["clock"][0] += 7200
    env["worker"].tick()
    assert statuses(env)["event-1"] == "PENDING"
    assert len(env["ses"].calls) == 1
    env["journal"].retry_failed(env["journal"].status()[0]["batch_id"])
    env["worker"].tick()
    assert len(env["ses"].calls) == 2


@pytest.mark.parametrize("field", ["account", "recipient", "destination", "provider", "attempt", "configuration", "batch", "sender"])
def test_unrelated_receipts_cannot_acknowledge_events(env, field):
    add_event(env)
    env["worker"].tick()
    event = receipt(env)
    if field == "account": event["mail"]["sendingAccountId"] = "999999999999"
    if field == "recipient": event["delivery"]["recipients"] = ["other@example.com"]
    if field == "destination": event["mail"]["destination"] = ["other@example.com"]
    if field == "provider": event["mail"]["messageId"] = "unrelated-message"
    if field == "attempt": event["mail"]["tags"]["pm_attempt_id"] = ["unknown"]
    if field == "configuration": event["mail"]["tags"]["ses:configuration-set"] = ["production"]
    if field == "batch": event["mail"]["tags"]["pm_batch_id"] = ["unknown"]
    if field == "sender": event["mail"]["source"] = "other@example.com"
    env["sqs"].push(event)
    env["worker"].tick()
    assert statuses(env)["event-1"] == "PENDING"
    assert not env["sqs"].deleted


def test_durable_receipt_precedes_sqs_delete(env, monkeypatch):
    add_event(env)
    env["worker"].tick()
    env["sqs"].push(receipt(env))
    def disk_full(*args):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(env["journal"], "record_receipt", disk_full)
    with pytest.raises(sqlite3.OperationalError):
        env["worker"].tick()
    assert not env["sqs"].deleted
    assert statuses(env)["event-1"] == "PENDING"


def test_old_receipt_does_not_move_last_notified_backwards(env):
    add_event(env)
    with env["connect"]() as db:
        db.execute("UPDATE state SET last_notified_at='2026-11-20 20:00:00'")
    env["worker"].tick()
    env["sqs"].push(receipt(env))
    env["worker"].tick()
    with env["connect"]() as db:
        assert db.execute("SELECT last_notified_at FROM state").fetchone()[0] == "2026-11-20 20:00:00"


def test_batch_boundaries_do_not_acknowledge_other_emails(env):
    for i in range(51):
        add_event(env, f"event-{i:03}")
    env["worker"].tick()
    assert len(env["ses"].calls) == 2
    # Batches created at the same instant can be sent in either order. Confirm
    # the single-event email by its actual content, not an assumed send index.
    single_email = next(i for i, call in enumerate(env["ses"].calls)
                        if call["Content"]["Simple"]["Subject"]["Data"]
                        == "Predictive maintenance: 1 drift event(s)")
    env["sqs"].push(receipt(env, call_index=single_email))
    env["worker"].tick()
    assert {key for key, status in statuses(env).items() if status == "SENT"} == {"event-050"}


def test_environment_cannot_reuse_another_journal(env):
    different = replace(env["settings"], catalog="predictivemaintenancecatalog")
    with pytest.raises(ValueError, match="different environment"):
        w.Journal(different.database, different.scope)


@pytest.mark.parametrize("change", [
    {"catalog": "catalog;DROP TABLE events"}, {"sender": "a@example.com\nBcc: x@example.com"},
    {"recipient": "a@example.com,b@example.com"}, {"account_id": "not-an-account"},
    {"queue_url": "https://attacker.example/queue"}, {"configuration_set": "bad/name"},
    {"poll_seconds": 0}, {"retry_seconds": 1}, {"databricks_host": "https://wrong/path"},
])
def test_invalid_configuration_fails_before_any_network_request(env, change):
    with pytest.raises(ValueError):
        replace(env["settings"], **change)
