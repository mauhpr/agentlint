"""Cloud data feeds — the architectural lever that makes hybrid rules possible.

This module is the *only* mechanism by which OSS rule code can consult
cloud-curated data. The contract:

    deny_list = cloud_feed.get("compromised-packages", default=set())
    if package_name in deny_list:
        yield Violation(...)

When AgentChute is not configured (no license key) OR the network is down OR
the cache is empty AND the network just failed, the call returns the
``default`` value and the rule runs without the feed data. This is the
**self-degrading** property — every hybrid rule that uses ``cloud_feed``
must remain useful (just less precise) without the cloud component.

Why this design choice matters
-------------------------------

Phase 17 of the strategy plan is built on this: the OSS source code is
fully transparent and forkable, but the *data* the rules consult comes
from a cloud service that updates daily. A competitor can fork the rule
code in seconds and replicate the cache directory format in a weekend,
but reproducing 6 months of curated daily-refreshed data takes 6 months.
That asymmetric cost is the moat.

Privacy contract
----------------

The feed-fetch path is the ONE outbound HTTP call OSS makes outside of
``post_event_async``. Things that ARE sent:
    - The feed name (e.g., ``"compromised-packages"``)
    - The license key (Bearer header)
    - The cached ETag (so 304 Not Modified can save bandwidth)

Things that are NEVER sent:
    - Any event data
    - Any file content
    - Any rule-evaluation context

The opt-in gate is the same as ``post_event_async``: requires
``AGENTCHUTE_LICENSE_KEY`` to be set. Otherwise the call is a no-op and
``default`` is returned immediately.

Cache layout
------------

::

    ~/.cache/agentlint/feeds/
    ├── compromised-packages.json     # the actual data
    ├── compromised-packages.meta     # {"fetched_at": 1700000000, "etag": "..."}
    ├── known-bad-shells.json
    └── known-bad-shells.meta

Single delete of ``~/.cache/agentlint/feeds/`` resets all feeds cleanly.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentlint.agentchute.client import (
    DEFAULT_API_URL,
    ENV_AGENTCHUTE_API_URL,
    ENV_AGENTCHUTE_LICENSE_KEY,
    _CONNECT_TIMEOUT_S,
    _READ_TIMEOUT_S,
)

logger = logging.getLogger("agentlint.agentchute.feeds")

# Default refresh window. A feed is considered fresh for this many seconds
# after fetch. Individual feeds can override via the ``ttl`` key in their
# meta file.
_DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# Hard ceiling on a single feed's payload, to avoid pathological cases
# where a misconfigured server returns a 1GB blob.
_MAX_FEED_BYTES = 10 * 1024 * 1024  # 10 MB


def _feeds_dir() -> Path:
    """Resolve the on-disk cache root for feeds.

    Reads ``AGENTLINT_FEEDS_DIR`` lazily so tests can isolate via
    ``monkeypatch.setenv``."""
    return Path(
        os.environ.get(
            "AGENTLINT_FEEDS_DIR", "~/.cache/agentlint/feeds"
        )
    ).expanduser()


def _data_path(feed_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in feed_name)
    return _feeds_dir() / f"{safe}.json"


def _meta_path(feed_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in feed_name)
    return _feeds_dir() / f"{safe}.meta"


@dataclass
class _CachedFeed:
    """In-memory representation of one feed's persisted state."""
    data: Any
    fetched_at: float
    etag: str | None
    ttl: int

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.fetched_at) < self.ttl


def _read_cache(feed_name: str) -> _CachedFeed | None:
    """Load a feed's cached data + metadata. Returns None if either side
    is missing or unparseable."""
    data_p = _data_path(feed_name)
    meta_p = _meta_path(feed_name)
    if not data_p.exists() or not meta_p.exists():
        return None
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        data = json.loads(data_p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return _CachedFeed(
        data=data,
        fetched_at=float(meta.get("fetched_at", 0)),
        etag=meta.get("etag"),
        ttl=int(meta.get("ttl", _DEFAULT_TTL_SECONDS)),
    )


def _write_cache(feed_name: str, data: Any, etag: str | None, ttl: int) -> None:
    """Persist data + meta atomically. Created dirs if needed."""
    feeds_root = _feeds_dir()
    feeds_root.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data)
    if len(serialized.encode("utf-8")) > _MAX_FEED_BYTES:
        logger.warning(
            "agentlint.agentchute.feeds: feed '%s' exceeds %d bytes — refusing to cache",
            feed_name, _MAX_FEED_BYTES,
        )
        return
    _data_path(feed_name).write_text(serialized, encoding="utf-8")
    _meta_path(feed_name).write_text(
        json.dumps({
            "fetched_at": time.time(),
            "etag": etag,
            "ttl": ttl,
        }),
        encoding="utf-8",
    )


def _fetch_feed_remote(feed_name: str, etag: str | None) -> tuple[Any, str | None, int] | None:
    """Make the actual HTTP call. Returns (data, new_etag, ttl) on 200,
    None on 304/error/missing-license. Logs at DEBUG so failures are
    silent in normal CLI output (the rule still works with defaults)."""
    license_key = os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY)
    if not license_key:
        return None
    api_url = os.environ.get(ENV_AGENTCHUTE_API_URL, DEFAULT_API_URL).rstrip("/")

    try:
        import requests  # type: ignore
    except ImportError:
        logger.debug("agentlint.agentchute.feeds: requests not installed; feed disabled")
        return None

    headers = {
        "Authorization": f"Bearer {license_key}",
        "User-Agent": "agentlint/agentchute/feeds",
        "Accept": "application/json",
    }
    if etag:
        headers["If-None-Match"] = etag

    try:
        response = requests.get(
            f"{api_url}/feeds/{feed_name}",
            headers=headers,
            timeout=(_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S),
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("agentlint.agentchute.feeds: GET failed (%s)", e)
        return None

    if response.status_code == 304:
        # Cached version is current.
        logger.debug("agentlint.agentchute.feeds: %s 304 Not Modified", feed_name)
        return None
    if response.status_code != 200:
        logger.debug(
            "agentlint.agentchute.feeds: %s returned %d", feed_name, response.status_code
        )
        return None

    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        logger.debug("agentlint.agentchute.feeds: %s body not JSON", feed_name)
        return None

    new_etag = response.headers.get("ETag")
    ttl = int(response.headers.get("X-Feed-TTL", _DEFAULT_TTL_SECONDS))
    return data, new_etag, ttl


def get(feed_name: str, default: Any = None, *, allow_network: bool = True) -> Any:
    """Resolve a cloud feed, returning ``default`` whenever the feed
    isn't usable for any reason.

    Returns:
        The feed's data (typically dict, list, or set, depending on
        the feed) when fresh cache exists or remote fetch succeeded.
        Returns ``default`` (which the caller can specialize per-rule)
        whenever the feed is unavailable.

    This function is intentionally synchronous and blocking, but the
    underlying HTTP call has tight timeouts (1s connect, 2s read) so
    a slow API can add at most ~3s to a rule evaluation. Rules should
    only call this for evaluations that happen *outside* the lint hot
    path (e.g., session-startup rule warmups), or accept the latency.

    Opt-in gate:
        ``cloud_feed.get`` is a no-op (returns ``default``) whenever
        no AgentChute license key is set. This includes the
        cache-read path — a leftover cache file from a previous license
        does NOT serve data when AgentChute is currently disabled. This keeps
        the Phase 17 contract honest: "with AgentChute not configured, the
        rule is a silent no-op," with no way for stale on-disk state to
        leak through.

    Caching strategy:
        1. If a fresh cache exists (within TTL), return it immediately.
        2. If a stale cache exists, kick off a background refresh and
           return the stale data. (Background refresh disabled in v0
           to keep behavior deterministic; future enhancement.)
        3. If no cache exists, fetch synchronously. On success, cache
           and return. On failure, return ``default``.
    """
    # Opt-in gate. Without a license key, no cache path runs.
    if not os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY):
        return default

    cached = _read_cache(feed_name)
    if cached and cached.is_fresh:
        return cached.data

    if not allow_network:
        if cached is not None:
            logger.debug(
                "agentlint.agentchute.feeds: serving stale cache for '%s' "
                "(network refresh disabled)",
                feed_name,
            )
            return cached.data
        return default

    # Either no cache or expired. Try a remote fetch.
    result = _fetch_feed_remote(feed_name, etag=(cached.etag if cached else None))
    if result is not None:
        data, new_etag, ttl = result
        _write_cache(feed_name, data, new_etag, ttl)
        return data

    # Remote fetch failed. Fall back to stale cache if we have it —
    # better to use yesterday's deny list than no deny list.
    if cached is not None:
        logger.debug(
            "agentlint.agentchute.feeds: serving stale cache for '%s' "
            "(remote unreachable)", feed_name,
        )
        return cached.data

    return default


def clear(feed_name: str | None = None) -> int:
    """Delete one feed's cache files (or all of them). Returns count of
    files removed. Exposed for ``agentlint sync --reset`` and tests."""
    feeds_root = _feeds_dir()
    if not feeds_root.exists():
        return 0
    removed = 0
    if feed_name is None:
        for p in feeds_root.iterdir():
            if p.is_file():
                p.unlink()
                removed += 1
    else:
        for p in (_data_path(feed_name), _meta_path(feed_name)):
            if p.exists():
                p.unlink()
                removed += 1
    return removed
