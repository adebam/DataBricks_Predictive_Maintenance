from threading import RLock

import pandas as pd
from cachetools import TTLCache

from config import settings

_cache = TTLCache(maxsize=64, ttl=max(5, settings.cache_seconds))
_cache_lock = RLock()


def query_df(query: str) -> pd.DataFrame:
    """Execute a read-only Databricks SQL query and cache its result briefly."""
    with _cache_lock:
        cached = _cache.get(query)
        if cached is not None:
            return cached.copy()

    if not settings.has_databricks_credentials:
        raise RuntimeError(
            "Databricks SQL connection is not configured. Set DATABRICKS_SERVER_HOSTNAME, "
            "DATABRICKS_HTTP_PATH and either DATABRICKS_TOKEN or "
            "DATABRICKS_CLIENT_ID/DATABRICKS_CLIENT_SECRET."
        )

    from databricks import sql

    connect_kwargs = {
        "server_hostname": settings.databricks_host,
        "http_path": settings.databricks_http_path,
    }
    if settings.databricks_client_id and settings.databricks_client_secret:
        # OAuth M2M for unattended EC2 deployment; PAT supported for local setup.
        from databricks.sdk.core import Config, oauth_service_principal

        def credential_provider():
            config = Config(
                host=f"https://{settings.databricks_host}",
                client_id=settings.databricks_client_id,
                client_secret=settings.databricks_client_secret,
            )
            return oauth_service_principal(config)

        connect_kwargs["credentials_provider"] = credential_provider
    else:
        connect_kwargs["access_token"] = settings.databricks_token

    with sql.connect(**connect_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [description[0] for description in (cursor.description or [])]

    frame = pd.DataFrame(rows, columns=columns)
    with _cache_lock:
        _cache[query] = frame.copy()
    return frame


def clear_query_cache() -> None:
    with _cache_lock:
        _cache.clear()
