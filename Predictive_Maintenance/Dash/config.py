import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

_TABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){1,2}$")


def table_name(env_name: str, default: str = "") -> str:
    value = os.getenv(env_name, default).strip()
    if value and not _TABLE_PATTERN.fullmatch(value):
        raise ValueError(
            f"{env_name} must be a two- or three-part Unity Catalog table name; got {value!r}"
        )
    return value


@dataclass(frozen=True)
class Settings:
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
    databricks_host: str = os.getenv("DATABRICKS_SERVER_HOSTNAME", "").replace("https://", "").strip("/")
    databricks_http_path: str = os.getenv("DATABRICKS_HTTP_PATH", "")
    databricks_token: str = os.getenv("DATABRICKS_TOKEN", "")
    databricks_client_id: str = os.getenv("DATABRICKS_CLIENT_ID", "")
    databricks_client_secret: str = os.getenv("DATABRICKS_CLIENT_SECRET", "")
    cache_seconds: int = int(os.getenv("QUERY_CACHE_SECONDS", "45"))

    predictions_table: str = table_name(
        "PREDICTIONS_TABLE", "predictivemaintenancecatalog.gold_data.test_failure_predictions"
    )
    drift_reference_table: str = table_name(
        "DRIFT_REFERENCE_TABLE",
        "predictivemaintenancecatalog.gold_data.all_features",
    )
    drift_table: str = table_name(
        "DRIFT_TABLE",
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift",
    )
    drift_rolling_table: str = table_name(
        "DRIFT_ROLLING_TABLE",
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_rolling",
    )
    alerts_table: str = table_name(
        "ALERTS_TABLE",
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alerts",
    )
    alert_state_table: str = table_name(
        "ALERT_STATE_TABLE",
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alert_state",
    )
    alert_events_table: str = table_name(
        "ALERT_EVENTS_TABLE",
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alert_events",
    )
    # Notebook 50 attaches the original CSV filename to each UDI here.
    monitoring_table: str = table_name(
        "MONITORING_TABLE", "predictivemaintenancecatalog.gold_data.prediction_monitoring"
    )
    # Notebook 30 adds _ingest_timestamp to Bronze records.
    bronze_table: str = table_name(
        "BRONZE_TABLE", "predictivemaintenancecatalog.bronze_data_not_quality_checked.streaming"
    )
    current_features_table: str = table_name(
        "CURRENT_FEATURES_TABLE",
        "predictivemaintenancecatalog.gold_data.streaming",
    )
    # Optional legacy run status table override. When unset, use Databricks
    # Lakeflow's SQL-queryable system tables.
    pipeline_status_table: str = table_name("PIPELINE_STATUS_TABLE", "")
    monitored_job_ids: tuple[str, ...] = tuple(
        job_id.strip() for job_id in os.getenv(
            "MONITORED_JOB_IDS",
            "1093257342514742,988061660710201,195467107464674,65480912120821",
        ).split(",")
        if job_id.strip().isdigit()
    )

    @property
    def has_databricks_credentials(self) -> bool:
        has_auth = bool(self.databricks_token) or bool(
            self.databricks_client_id and self.databricks_client_secret
        )
        return bool(self.databricks_host and self.databricks_http_path and has_auth)


settings = Settings()
