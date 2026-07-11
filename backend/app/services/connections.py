from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.services.storage import (
    clear_source_cache,
    connect,
    load_user_connection_payload,
    load_user_connection_payloads,
    save_user_connection_payload,
)


ConnectionSource = Literal["ibkr", "binance"]


class UserConnectionConfig(BaseModel):
    source: ConnectionSource
    disabled: bool = False
    updated_at: datetime | None = None
    ibkr_host: str | None = None
    ibkr_port: int | None = Field(default=None, ge=1, le=65535)
    ibkr_client_id: int | None = Field(default=None, ge=0)
    ibkr_flex_query_id: str | None = None
    ibkr_flex_token: str | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    binance_ledger_start_date: datetime | None = None


class UserConnectionUpdate(BaseModel):
    ibkr_host: str | None = None
    ibkr_port: int | None = Field(default=None, ge=1, le=65535)
    ibkr_client_id: int | None = Field(default=None, ge=0)
    ibkr_flex_query_id: str | None = None
    ibkr_flex_token: str | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    binance_ledger_start_date: datetime | None = None


class UserConnectionPublic(BaseModel):
    source: ConnectionSource
    label: str
    configured: bool
    updated_at: datetime | None = None
    ibkr_host: str | None = None
    ibkr_port: int | None = None
    ibkr_client_id: int | None = None
    ibkr_flex_query_id: str | None = None
    ibkr_flex_token_configured: bool = False
    ibkr_flex_token_preview: str | None = None
    binance_api_key_configured: bool = False
    binance_api_key_preview: str | None = None
    binance_api_secret_configured: bool = False
    binance_api_secret_preview: str | None = None
    binance_ledger_start_date: datetime | None = None


CONNECTION_LABELS: dict[ConnectionSource, str] = {
    "ibkr": "Interactive Brokers",
    "binance": "Binance",
}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _preview_secret(value: str | None) -> str | None:
    if not value:
        return None
    return f"****{value[-4:]}" if len(value) > 4 else "****"


def _public_config(config: UserConnectionConfig | None, source: ConnectionSource) -> UserConnectionPublic:
    if config is None or config.disabled:
        return UserConnectionPublic(
            source=source,
            label=CONNECTION_LABELS[source],
            configured=False,
            ibkr_host="127.0.0.1" if source == "ibkr" else None,
            ibkr_port=7497 if source == "ibkr" else None,
            ibkr_client_id=1 if source == "ibkr" else None,
            ibkr_flex_query_id="1554875" if source == "ibkr" else None,
        )

    if source == "ibkr":
        return UserConnectionPublic(
            source=source,
            label=CONNECTION_LABELS[source],
            configured=True,
            updated_at=config.updated_at,
            ibkr_host=config.ibkr_host or "127.0.0.1",
            ibkr_port=config.ibkr_port or 7497,
            ibkr_client_id=config.ibkr_client_id if config.ibkr_client_id is not None else 1,
            ibkr_flex_query_id=config.ibkr_flex_query_id or "1554875",
            ibkr_flex_token_configured=bool(config.ibkr_flex_token),
            ibkr_flex_token_preview=_preview_secret(config.ibkr_flex_token),
        )

    return UserConnectionPublic(
        source=source,
        label=CONNECTION_LABELS[source],
        configured=True,
        updated_at=config.updated_at,
        binance_api_key_configured=bool(config.binance_api_key),
        binance_api_key_preview=_preview_secret(config.binance_api_key),
        binance_api_secret_configured=bool(config.binance_api_secret),
        binance_api_secret_preview=_preview_secret(config.binance_api_secret),
        binance_ledger_start_date=config.binance_ledger_start_date,
    )


def _load_config_by_source(settings: Settings, source: ConnectionSource) -> UserConnectionConfig | None:
    with connect(settings.data_dir) as conn:
        row = load_user_connection_payload(conn, source)
    if row is None:
        return None
    payload, updated_at = row
    try:
        config = UserConnectionConfig.model_validate_json(payload)
    except ValidationError:
        return None
    return config.model_copy(update={"updated_at": config.updated_at or updated_at})


def _save_config(settings: Settings, config: UserConnectionConfig) -> UserConnectionConfig:
    saved = config.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    with connect(settings.data_dir) as conn:
        save_user_connection_payload(
            conn,
            saved.source,
            saved.updated_at or datetime.now(timezone.utc),
            saved.model_dump_json(),
        )
        conn.commit()
    return saved


def _ibkr_env_config(settings: Settings) -> UserConnectionConfig | None:
    has_non_default = (
        settings.ibkr_host != "127.0.0.1"
        or settings.ibkr_port != 7497
        or settings.ibkr_client_id != 1
        or settings.ibkr_flex_query_id != "1554875"
        or bool(settings.ibkr_flex_token)
    )
    if not has_non_default:
        return None
    return UserConnectionConfig(
        source="ibkr",
        ibkr_host=settings.ibkr_host,
        ibkr_port=settings.ibkr_port,
        ibkr_client_id=settings.ibkr_client_id,
        ibkr_flex_query_id=settings.ibkr_flex_query_id,
        ibkr_flex_token=settings.ibkr_flex_token,
    )


def _binance_env_config(settings: Settings) -> UserConnectionConfig | None:
    if not settings.binance_api_key and not settings.binance_api_secret:
        return None
    return UserConnectionConfig(
        source="binance",
        binance_api_key=settings.binance_api_key,
        binance_api_secret=settings.binance_api_secret,
        binance_ledger_start_date=settings.binance_ledger_start_date,
    )


def migrate_env_connections(settings: Settings) -> None:
    for source, env_config in [
        ("ibkr", _ibkr_env_config(settings)),
        ("binance", _binance_env_config(settings)),
    ]:
        if env_config is None:
            continue
        existing = _load_config_by_source(settings, source)  # type: ignore[arg-type]
        if existing is None:
            _save_config(settings, env_config)


def load_user_connections(settings: Settings) -> list[UserConnectionPublic]:
    migrate_env_connections(settings)
    configs = {source: _load_config_by_source(settings, source) for source in CONNECTION_LABELS}
    return [_public_config(configs[source], source) for source in CONNECTION_LABELS]


def save_user_connection(
    settings: Settings,
    source: ConnectionSource,
    request: UserConnectionUpdate,
) -> UserConnectionPublic:
    current = _load_config_by_source(settings, source) or (
        _ibkr_env_config(settings) if source == "ibkr" else _binance_env_config(settings)
    ) or UserConnectionConfig(source=source)

    update: dict[str, object | None] = {}
    update["disabled"] = False
    if source == "ibkr":
        if request.ibkr_host is not None:
            update["ibkr_host"] = _clean_text(request.ibkr_host)
        if request.ibkr_port is not None:
            update["ibkr_port"] = request.ibkr_port
        if request.ibkr_client_id is not None:
            update["ibkr_client_id"] = request.ibkr_client_id
        if request.ibkr_flex_query_id is not None:
            update["ibkr_flex_query_id"] = _clean_text(request.ibkr_flex_query_id)
        if request.ibkr_flex_token is not None:
            update["ibkr_flex_token"] = _clean_text(request.ibkr_flex_token)
    else:
        if request.binance_api_key is not None:
            update["binance_api_key"] = _clean_text(request.binance_api_key)
        if request.binance_api_secret is not None:
            update["binance_api_secret"] = _clean_text(request.binance_api_secret)
        if request.binance_ledger_start_date is not None:
            update["binance_ledger_start_date"] = request.binance_ledger_start_date

    saved = _save_config(settings, current.model_copy(update=update))
    return _public_config(saved, source)


def disconnect_user_connection(settings: Settings, source: ConnectionSource) -> UserConnectionPublic:
    disabled = UserConnectionConfig(source=source, disabled=True, updated_at=datetime.now(timezone.utc))
    with connect(settings.data_dir) as conn:
        save_user_connection_payload(
            conn,
            source,
            disabled.updated_at or datetime.now(timezone.utc),
            disabled.model_dump_json(),
        )
        clear_source_cache(conn, source)
        conn.commit()
    return _public_config(disabled, source)


def load_connection_overrides(data_dir) -> dict[ConnectionSource, UserConnectionConfig]:
    with connect(data_dir) as conn:
        rows = load_user_connection_payloads(conn)
    configs: dict[ConnectionSource, UserConnectionConfig] = {}
    for source, updated_at, payload in rows:
        if source not in CONNECTION_LABELS:
            continue
        try:
            config = UserConnectionConfig.model_validate_json(payload)
        except ValidationError:
            continue
        configs[source] = config.model_copy(update={"updated_at": config.updated_at or updated_at})
    return configs
