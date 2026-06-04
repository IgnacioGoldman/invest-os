from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    retries: int = 3
    backoff_seconds: float = 1.0
    timeout_seconds: float = 20.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> Any:
    config = retry_config or RetryConfig()
    last_error: Exception | None = None

    for attempt in range(config.retries + 1):
        try:
            response = session.get(url, params=params, timeout=config.timeout_seconds)
            if response.status_code not in config.retry_statuses:
                response.raise_for_status()
                return response.json()

            last_error = requests.HTTPError(f"{response.status_code} response from {url}")
            if attempt == config.retries:
                response.raise_for_status()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == config.retries:
                raise

        sleep_for = config.backoff_seconds * (2**attempt)
        logger.warning("Retrying FMP request after %.1fs: %s", sleep_for, last_error)
        time.sleep(sleep_for)

    if last_error:
        raise last_error
    raise RuntimeError(f"Request failed without an error: {url}")

