"""AgentChute sync — opt-in cloud reporting.

This module forwards locally-generated event recordings to a hosted
AgentChute server, so a Head of Engineering can see what their org's
AI agents are doing across every developer's machine.

AgentChute is local-first: hooks write privacy-safe events to a durable
local queue, then a bounded background flusher uploads them later.

Privacy contract (verified by ``tests/test_agentchute_client.py``):
    - Only the metadata-summary dict produced by
      ``recorder.summarize_tool_input`` ever leaves the machine.
    - File contents, raw prompts, and full Bash commands are NEVER
      transmitted. Bash commands are truncated at 200 chars by the
      summarizer; Write/Edit only emit lengths and paths.
    - The user opts in via ``AGENTCHUTE_ENABLED=true`` or
      ``agentchute.enabled: true`` in agentlint.yml. Off by default.
    - Hook evaluation NEVER waits for the network and NEVER fails because
      AgentChute is down.

Public surface:
    is_agentchute_enabled(config) -> bool
    enqueue_event(event: dict, session_key: str) -> str | None
    flush_queue() -> FlushResult
"""

from agentlint.agentchute import feeds
from agentlint.agentchute.client import (
    AgentChuteClient,
    is_agentchute_enabled,
    post_event_async,
)
from agentlint.agentchute.queue import FlushResult, enqueue_event, flush_queue, trigger_background_flush
from agentlint.agentchute.sync import SyncResult, sync_recordings

# Convenience: ``from agentlint.agentchute import cloud_feed`` then
# ``cloud_feed.get("compromised-packages", default=set())``.
cloud_feed = feeds

__all__ = [
    "AgentChuteClient",
    "FlushResult",
    "SyncResult",
    "cloud_feed",
    "enqueue_event",
    "feeds",
    "flush_queue",
    "is_agentchute_enabled",
    "post_event_async",
    "sync_recordings",
    "trigger_background_flush",
]
