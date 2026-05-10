"""Tests for ``agentlint.agentchute.feeds`` (the cloud_feed primitive).

Coverage focuses on the four properties that make hybrid rules safe:

  1. **Self-degrading**: returns ``default`` when no license key, no
     network, no cache. Rules using a feed must remain runnable.
  2. **Privacy contract**: feed-fetch sends only feed_name + license,
     never event data or file content.
  3. **Cache freshness**: 24h default TTL honored. Within window =
     no network call. Past window = re-fetch.
  4. **Stale-fallback**: when network fails after cache expiry, return
     stale cache rather than ``default``. Stale data > no data.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def isolated_feed_cache(tmp_path, monkeypatch):
    """Point feeds at a tmp directory so tests don't touch the real cache."""
    feeds_dir = tmp_path / "feeds"
    monkeypatch.setenv("AGENTLINT_FEEDS_DIR", str(feeds_dir))
    yield feeds_dir


@pytest.fixture
def feed_creds(monkeypatch):
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    yield


# ---------- self-degrading: no license key ----------


def test_returns_default_when_no_license_key(isolated_feed_cache, monkeypatch):
    """Without a license key, get() must return default without ever
    touching the network."""
    monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
    from agentlint.agentchute import cloud_feed

    with patch("requests.get") as mock_get:
        result = cloud_feed.get("compromised-packages", default=set())
    mock_get.assert_not_called()
    assert result == set()


def test_existing_cache_does_not_leak_when_license_key_unset(
    isolated_feed_cache, monkeypatch
):
    """REGRESSION (Phase 19A): cache files left behind from a previous
    licensed session must NOT serve data when the license key is
    currently unset.

    Without this gate, a developer who tried AgentChute once, generated
    a cache, and then unset the env var would still see AgentChute rules
    fire from the stale cache — violating the Phase 17 contract that
    OSS users without a license get a silent no-op.
    """
    import time
    from agentlint.agentchute import cloud_feed

    # Pre-populate a cache file as if a previous licensed run created it
    feed_data = ["pretend-this-was-cached", "from-an-earlier-run"]
    cloud_feed._write_cache(  # noqa: SLF001
        "compromised-packages",
        feed_data,
        etag="cached-etag",
        ttl=24 * 3600,
    )
    # Sanity: writing the cache landed on disk
    cached = cloud_feed._read_cache("compromised-packages")  # noqa: SLF001
    assert cached is not None
    assert cached.is_fresh

    # Now simulate the user removing their license key
    monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)

    # The cache is on disk and "fresh" by TTL standards. It must NOT
    # be returned. Network must NOT be called either (no license key).
    with patch("requests.get") as mock_get:
        result = cloud_feed.get("compromised-packages", default=set())

    mock_get.assert_not_called()
    assert result == set(), (
        "stale cache leaked through opt-in gate — Phase 17 contract violated"
    )
    _ = time  # silence unused import linter false-positive in some setups


def test_returns_default_when_network_fails_with_no_cache(
    isolated_feed_cache, feed_creds
):
    """First-ever fetch fails → return default (rule still runs, just
    without the cloud-curated data)."""
    from agentlint.agentchute import cloud_feed

    def _fail(*a, **k):
        import requests as _r

        raise _r.exceptions.ConnectionError("simulated DNS failure")

    with patch("requests.get", side_effect=_fail):
        result = cloud_feed.get("compromised-packages", default=["fallback"])
    assert result == ["fallback"]


def test_cache_only_read_does_not_fetch_with_no_cache(isolated_feed_cache, feed_creds):
    """Hook hot paths use cache-only reads so an empty cache cannot block on HTTP."""
    from agentlint.agentchute import cloud_feed

    with patch("requests.get") as mock_get:
        result = cloud_feed.get(
            "compromised-packages", default=["fallback"], allow_network=False
        )

    mock_get.assert_not_called()
    assert result == ["fallback"]


def test_cache_only_read_serves_stale_cache(isolated_feed_cache, feed_creds):
    from agentlint.agentchute import cloud_feed
    from agentlint.agentchute import feeds as feeds_module

    fake_response = MagicMock(status_code=200, headers={"ETag": "v", "X-Feed-TTL": "3600"})
    fake_response.json.return_value = ["cached"]
    with patch("requests.get", return_value=fake_response):
        cloud_feed.get("cache-only", default=[])

    meta_path = feeds_module._meta_path("cache-only")
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = 0
    meta["ttl"] = 1
    meta_path.write_text(json.dumps(meta))

    with patch("requests.get") as mock_get:
        result = cloud_feed.get("cache-only", default=[], allow_network=False)

    mock_get.assert_not_called()
    assert result == ["cached"]


# ---------- successful fetch + caching ----------


def test_fetches_remote_and_caches_on_success(isolated_feed_cache, feed_creds):
    """Remote returns data → write cache → subsequent reads hit cache."""
    from agentlint.agentchute import cloud_feed

    fake_data = ["@evil/package@1.0.0", "leftpad-injected@2.0.0"]
    fake_response = MagicMock(
        status_code=200,
        headers={"ETag": "abc123", "X-Feed-TTL": "3600"},
    )
    fake_response.json.return_value = fake_data

    with patch("requests.get", return_value=fake_response) as mock_get:
        first = cloud_feed.get("compromised-packages", default=[])
        second = cloud_feed.get("compromised-packages", default=[])

    assert first == fake_data
    assert second == fake_data
    # ONE network call total — second call hits the fresh cache.
    assert mock_get.call_count == 1


def test_invalid_cache_and_remote_failures_return_default(isolated_feed_cache, feed_creds):
    from agentlint.agentchute import cloud_feed

    isolated_feed_cache.mkdir(parents=True)
    (isolated_feed_cache / "bad.json").write_text("{bad", encoding="utf-8")
    (isolated_feed_cache / "bad.meta").write_text("{bad", encoding="utf-8")
    assert cloud_feed._read_cache("bad") is None  # noqa: SLF001

    response = MagicMock(status_code=500, headers={})
    with patch("requests.get", return_value=response):
        assert cloud_feed.get("bad", default=["fallback"]) == ["fallback"]

    response = MagicMock(status_code=200, headers={})
    response.json.side_effect = ValueError("not json")
    with patch("requests.get", return_value=response):
        assert cloud_feed.get("bad-json", default=["fallback"]) == ["fallback"]


def test_write_cache_refuses_oversized_payload(isolated_feed_cache):
    from agentlint.agentchute import cloud_feed

    cloud_feed._write_cache("huge", "x" * (10 * 1024 * 1024 + 1), etag=None, ttl=60)  # noqa: SLF001

    assert not (isolated_feed_cache / "huge.json").exists()
    assert not (isolated_feed_cache / "huge.meta").exists()


def test_agentchute_env_alias_fetches_remote(isolated_feed_cache, monkeypatch):
    """AgentChute-named env vars work for cloud feed fetches."""
    from agentlint.agentchute import cloud_feed

    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    fake_response = MagicMock(status_code=200, headers={"ETag": "v1"})
    fake_response.json.return_value = ["x"]

    with patch("requests.get", return_value=fake_response) as mock_get:
        result = cloud_feed.get("test-feed", default=[])

    assert result == ["x"]
    headers = mock_get.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer ac_team_test_xxx"


def test_cache_files_persist_to_disk(isolated_feed_cache, feed_creds):
    """The data + meta should be on disk after a successful fetch."""
    from agentlint.agentchute import cloud_feed

    fake_response = MagicMock(
        status_code=200,
        headers={"ETag": "v1", "X-Feed-TTL": "3600"},
    )
    fake_response.json.return_value = {"banned": ["a", "b"]}

    with patch("requests.get", return_value=fake_response):
        cloud_feed.get("test-feed", default={})

    data_file = isolated_feed_cache / "test-feed.json"
    meta_file = isolated_feed_cache / "test-feed.meta"
    assert data_file.exists()
    assert meta_file.exists()
    assert json.loads(data_file.read_text()) == {"banned": ["a", "b"]}
    meta = json.loads(meta_file.read_text())
    assert meta["etag"] == "v1"
    assert meta["ttl"] == 3600


# ---------- TTL behavior ----------


def test_fresh_cache_does_not_hit_network(isolated_feed_cache, feed_creds):
    """If cache is within TTL, no remote call should be made."""
    from agentlint.agentchute import cloud_feed

    # Pre-populate the cache with fresh data.
    fake_response = MagicMock(
        status_code=200,
        headers={"ETag": "abc", "X-Feed-TTL": str(24 * 60 * 60)},
    )
    fake_response.json.return_value = ["x", "y"]

    with patch("requests.get", return_value=fake_response):
        cloud_feed.get("known-bad-shells", default=[])

    # Now a second call: cache is fresh, must NOT hit the network.
    with patch("requests.get") as mock_get:
        result = cloud_feed.get("known-bad-shells", default=[])
    mock_get.assert_not_called()
    assert result == ["x", "y"]


def test_expired_cache_triggers_refetch(isolated_feed_cache, feed_creds):
    """Cache past TTL → re-fetch."""
    from agentlint.agentchute import cloud_feed
    from agentlint.agentchute import feeds as feeds_module

    # Pre-populate cache with TTL of 0 so it's instantly stale.
    pre_response = MagicMock(
        status_code=200,
        headers={"ETag": "old", "X-Feed-TTL": "0"},
    )
    pre_response.json.return_value = ["old-data"]
    with patch("requests.get", return_value=pre_response):
        cloud_feed.get("test-feed", default=[])

    # Manually backdate the meta file to ensure expired status.
    meta_path = feeds_module._meta_path("test-feed")
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = 0  # epoch, definitely expired
    meta["ttl"] = 1
    meta_path.write_text(json.dumps(meta))

    # Now the next call should re-fetch.
    new_response = MagicMock(
        status_code=200,
        headers={"ETag": "new", "X-Feed-TTL": "3600"},
    )
    new_response.json.return_value = ["new-data"]
    with patch("requests.get", return_value=new_response) as mock_get:
        result = cloud_feed.get("test-feed", default=[])
    mock_get.assert_called_once()
    assert result == ["new-data"]


# ---------- stale-fallback: network fails after cache expires ----------


def test_serves_stale_when_network_fails_after_expiry(
    isolated_feed_cache, feed_creds
):
    """Cache expired AND network fails → return stale cache, never default.
    This is the 'yesterday's deny list > no deny list' property."""
    from agentlint.agentchute import cloud_feed
    from agentlint.agentchute import feeds as feeds_module

    # Pre-populate cache.
    pre_response = MagicMock(
        status_code=200, headers={"ETag": "v1", "X-Feed-TTL": "3600"}
    )
    pre_response.json.return_value = ["stale-but-real-data"]
    with patch("requests.get", return_value=pre_response):
        cloud_feed.get("test-feed", default=[])

    # Force expiry.
    meta_path = feeds_module._meta_path("test-feed")
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = 0
    meta["ttl"] = 1
    meta_path.write_text(json.dumps(meta))

    # Network call fails on refresh.
    def _fail(*a, **k):
        import requests as _r

        raise _r.exceptions.ConnectionError("simulated outage")

    with patch("requests.get", side_effect=_fail):
        # Should return the stale cache, NOT the default.
        result = cloud_feed.get("test-feed", default=["fallback"])

    assert result == ["stale-but-real-data"]


# ---------- privacy contract ----------


def test_feed_request_only_sends_license_and_etag(
    isolated_feed_cache, feed_creds
):
    """The outbound HTTP call must contain the license bearer token + etag,
    and must NOT contain any event data or content body."""
    from agentlint.agentchute import cloud_feed

    fake_response = MagicMock(
        status_code=200, headers={"ETag": "v1", "X-Feed-TTL": "3600"}
    )
    fake_response.json.return_value = []

    with patch("requests.get", return_value=fake_response) as mock_get:
        cloud_feed.get("compromised-packages", default=[])

    args, kwargs = mock_get.call_args
    # The call should be GET, not POST. No body == no leak surface.
    # Verify auth header sent, no JSON body.
    assert "json" not in kwargs, "feed fetch must not have a body"
    assert "data" not in kwargs, "feed fetch must not have a body"
    headers = kwargs.get("headers", {})
    assert headers.get("Authorization", "").startswith("Bearer ")
    assert headers.get("Authorization") == "Bearer ac_team_test_xxx"


def test_etag_is_sent_on_subsequent_request(isolated_feed_cache, feed_creds):
    """After first fetch caches an ETag, the next refetch attempt should
    include If-None-Match so the server can 304 and save bandwidth."""
    from agentlint.agentchute import cloud_feed
    from agentlint.agentchute import feeds as feeds_module

    pre_response = MagicMock(
        status_code=200, headers={"ETag": "v-abc-123", "X-Feed-TTL": "3600"}
    )
    pre_response.json.return_value = ["initial"]
    with patch("requests.get", return_value=pre_response):
        cloud_feed.get("test-feed", default=[])

    # Force expiry to trigger a refetch.
    meta_path = feeds_module._meta_path("test-feed")
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = 0
    meta["ttl"] = 1
    meta_path.write_text(json.dumps(meta))

    refresh_response = MagicMock(status_code=304, headers={})
    with patch("requests.get", return_value=refresh_response) as mock_get:
        cloud_feed.get("test-feed", default=[])

    headers = mock_get.call_args.kwargs.get("headers", {})
    assert headers.get("If-None-Match") == "v-abc-123"


def test_304_response_serves_existing_cache(isolated_feed_cache, feed_creds):
    """When the server says 304 (cache still current), return the cache
    we already have."""
    from agentlint.agentchute import cloud_feed
    from agentlint.agentchute import feeds as feeds_module

    pre_response = MagicMock(
        status_code=200, headers={"ETag": "v1", "X-Feed-TTL": "3600"}
    )
    pre_response.json.return_value = ["original-payload"]
    with patch("requests.get", return_value=pre_response):
        cloud_feed.get("test-feed", default=[])

    # Force expiry.
    meta_path = feeds_module._meta_path("test-feed")
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = 0
    meta["ttl"] = 1
    meta_path.write_text(json.dumps(meta))

    refresh_response = MagicMock(status_code=304, headers={})
    with patch("requests.get", return_value=refresh_response):
        result = cloud_feed.get("test-feed", default=[])

    assert result == ["original-payload"]


# ---------- clear() ----------


def test_clear_removes_specific_feed(isolated_feed_cache, feed_creds):
    """clear('foo') should remove only foo's data + meta, leaving others."""
    from agentlint.agentchute import cloud_feed

    fake = MagicMock(status_code=200, headers={"ETag": "v", "X-Feed-TTL": "3600"})
    fake.json.return_value = ["x"]
    with patch("requests.get", return_value=fake):
        cloud_feed.get("feed-a", default=[])
        cloud_feed.get("feed-b", default=[])

    removed = cloud_feed.clear("feed-a")
    assert removed == 2  # data + meta
    assert not (isolated_feed_cache / "feed-a.json").exists()
    assert not (isolated_feed_cache / "feed-a.meta").exists()
    assert (isolated_feed_cache / "feed-b.json").exists()


def test_clear_missing_cache_returns_zero(isolated_feed_cache):
    from agentlint.agentchute import cloud_feed

    assert cloud_feed.clear() == 0


def test_clear_all_removes_everything(isolated_feed_cache, feed_creds):
    """clear() with no arg wipes the entire feeds cache."""
    from agentlint.agentchute import cloud_feed

    fake = MagicMock(status_code=200, headers={"ETag": "v", "X-Feed-TTL": "3600"})
    fake.json.return_value = ["x"]
    with patch("requests.get", return_value=fake):
        cloud_feed.get("feed-a", default=[])
        cloud_feed.get("feed-b", default=[])

    removed = cloud_feed.clear()
    assert removed == 4
    # Directory exists but is empty.
    assert isolated_feed_cache.exists()
    assert not list(isolated_feed_cache.iterdir())


# ---------- usage example: a hybrid rule ----------


def test_hybrid_rule_uses_feed_with_default(isolated_feed_cache, monkeypatch):
    """End-to-end shape: a rule that uses cloud_feed.get(name, default).
    With no license key, the rule still runs — just sees default data."""
    monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
    from agentlint.agentchute import cloud_feed

    def hybrid_rule_check(package_name: str) -> bool:
        deny_list = cloud_feed.get("compromised-packages", default=set())
        return package_name in deny_list

    # Without AgentChute: always returns False (default empty set, nothing matches).
    assert hybrid_rule_check("@evil/package") is False
    assert hybrid_rule_check("safe-package") is False
