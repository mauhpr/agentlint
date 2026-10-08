"""HTTP client for AgentChute.

This module is the ONLY place AgentLint emits event network traffic. All other
code paths must funnel through ``AgentChuteClient`` so the privacy
guarantees, opt-in gate, and timeout/retry semantics are enforced
uniformly.

Design constraints:
    - Local-first: the lint hot path NEVER blocks on the network.
    - Hard failure isolation: if the API is down, the agent keeps working
      and the local AgentChute queue is still written. The background
      flusher will catch up when the network comes back.
    - Strict opt-in: off unless the user sets ``AGENTCHUTE_ENABLED=true``
      OR ``agentchute.enabled: true`` in agentlint.yml
      AND a license key is set.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from agentlint.agentchute.settings import (
    DEFAULT_API_URL,
    ENV_AGENTCHUTE_API_URL,
    ENV_AGENTCHUTE_ENABLED,
    ENV_AGENTCHUTE_LICENSE_KEY,
    get_api_url,
    get_license_key,
    is_agentchute_enabled,
)

__all__ = [
    "DEFAULT_API_URL",
    "ENV_AGENTCHUTE_API_URL",
    "ENV_AGENTCHUTE_ENABLED",
    "ENV_AGENTCHUTE_LICENSE_KEY",
    "AgentChuteClient",
    "is_agentchute_enabled",
    "post_event_async",
]

logger = logging.getLogger("agentlint.agentchute.client")

# Network timeouts. Conservative on purpose — if the API is slow, we want
# to drop the event and keep the agent moving, not block on a socket.
_CONNECT_TIMEOUT_S = 1.0
_READ_TIMEOUT_S = 2.0


@dataclass
class AgentChuteClient:
    """Configuration bundle for a single sync session. Independent
    instances are cheap; create one per ``agentlint agentchute flush`` invocation
    or per long-running process."""

    api_url: str
    license_key: str
    user_agent: str = "agentlint/agentchute"
    # Outcome of the most recent batch POST, for queue health reporting:
    # ok | rate_limited | server_error | auth_error | client_error | network_error
    last_outcome: str | None = field(default=None, compare=False)
    last_http_status: int | None = field(default=None, compare=False)
    retry_after_s: float | None = field(default=None, compare=False)

    @classmethod
    def from_env(cls) -> AgentChuteClient | None:
        """Build a client from env vars or local AgentChute credentials."""
        license_key = get_license_key()
        if not license_key:
            return None
        return cls(api_url=get_api_url(), license_key=license_key)

    def post_event(self, event: dict) -> bool:
        """Synchronous POST. Returns True on 2xx, False on any failure
        (including timeouts and network errors). Hook callers should enqueue
        locally and trigger the background flusher instead of calling this
        directly."""
        try:
            import requests  # lazy import — only paid when AgentChute is on
        except ImportError:
            logger.warning("agentlint.agentchute: requests not installed; sync disabled")
            return False

        try:
            response = requests.post(
                f"{self.api_url}/events",
                json=event,
                headers={
                    "Authorization": f"Bearer {self.license_key}",
                    "User-Agent": self.user_agent,
                    "Content-Type": "application/json",
                },
                timeout=(_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S),
            )
        except requests.exceptions.Timeout:
            logger.debug("agentlint.agentchute: POST timed out (event dropped)")
            return False
        except requests.exceptions.RequestException as e:
            logger.debug("agentlint.agentchute: POST failed (%s)", e)
            return False

        if 200 <= response.status_code < 300:
            return True

        # 401/403 = bad license. Log loudly so the user sees it.
        if response.status_code in (401, 403):
            logger.warning(
                "agentlint.agentchute: rejected by API (status %d). Check AGENTCHUTE_LICENSE_KEY.",
                response.status_code,
            )
        else:
            logger.debug("agentlint.agentchute: POST got status %d", response.status_code)
        return False

    def post_events_batch(self, events: list[dict]) -> dict | None:
        """Synchronous batch POST. Returns decoded response JSON on 2xx.

        The server accepts duplicate event IDs as success, allowing local
        retries after network failures without double-counting events.
        """
        self.last_outcome = None
        self.last_http_status = None
        self.retry_after_s = None
        if not events:
            return {"accepted": 0, "duplicates": 0, "failed": []}

        try:
            import requests  # lazy import — only paid when AgentChute is on
        except ImportError:
            logger.warning("agentlint.agentchute: requests not installed; batch flush disabled")
            self.last_outcome = "network_error"
            return None

        try:
            response = requests.post(
                f"{self.api_url}/events/batch",
                json={"events": events},
                headers={
                    "Authorization": f"Bearer {self.license_key}",
                    "User-Agent": self.user_agent,
                    "Content-Type": "application/json",
                },
                timeout=(_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S),
            )
        except requests.exceptions.Timeout:
            logger.debug("agentlint.agentchute: batch POST timed out")
            self.last_outcome = "network_error"
            return None
        except requests.exceptions.RequestException as e:
            logger.debug("agentlint.agentchute: batch POST failed (%s)", e)
            self.last_outcome = "network_error"
            return None

        status = response.status_code
        self.last_http_status = status if isinstance(status, int) else None
        if 200 <= response.status_code < 300:
            self.last_outcome = "ok"
            try:
                return response.json()
            except ValueError:
                return {"accepted": len(events), "duplicates": 0, "failed": []}

        if status == 429 or status == 503:
            self.last_outcome = "rate_limited" if status == 429 else "server_error"
            headers = getattr(response, "headers", None) or {}
            self.retry_after_s = parse_retry_after(headers.get("Retry-After"))
            logger.debug("agentlint.agentchute: batch POST throttled (status %d)", status)
            return None
        if isinstance(status, int) and status >= 500:
            self.last_outcome = "server_error"
        elif status in (401, 403):
            self.last_outcome = "auth_error"
        else:
            self.last_outcome = "client_error"

        if response.status_code in (401, 403):
            logger.warning(
                "agentlint.agentchute: rejected by API (status %d). Check AGENTCHUTE_LICENSE_KEY.",
                response.status_code,
            )
        else:
            logger.debug("agentlint.agentchute: batch POST got status %d", response.status_code)
        return None


def post_event_async(event: dict, config: Any | None = None) -> None:
    """Compatibility helper for direct best-effort event POSTs.

    The hook path uses the durable queue instead. This remains available for
    tests and debugging where callers explicitly want a one-shot async POST.
    """
    if not is_agentchute_enabled(config):
        return
    client = AgentChuteClient.from_env()
    if client is None:
        return
    thread = threading.Thread(
        target=_safe_post,
        args=(client, event),
        daemon=True,
        name="agentlint-agentchute-post",
    )
    thread.start()


def _safe_post(client: AgentChuteClient, event: dict) -> None:
    try:
        client.post_event(event)
    except Exception:  # noqa: BLE001
        logger.debug("agentlint.agentchute: post_event_async swallowed", exc_info=True)


_RETRY_AFTER_CAP_S = 3600.0


def parse_retry_after(value: object, *, now: float | None = None) -> float | None:
    """Parse a Retry-After header (delta seconds or HTTP date), capped at one hour."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        from email.utils import parsedate_to_datetime

        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        import time as _time

        seconds = when.timestamp() - (now if now is not None else _time.time())
    if seconds != seconds:  # NaN
        return None
    return max(0.0, min(_RETRY_AFTER_CAP_S, seconds))
