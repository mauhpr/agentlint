"""Queue-related Click commands.

Kept outside the main CLI module so queue presentation and lifecycle behavior
can evolve without adding more responsibilities to ``agentlint.cli``.
"""

from __future__ import annotations

import json
from typing import Any

import click


def register_queue_commands(main: Any) -> None:
    """Register the local AgentChute queue command group."""

    @main.group("queue")
    def queue_group() -> None:
        """Inspect and flush the local AgentChute queue."""

    @queue_group.command("status")
    def queue_status_command() -> None:
        """Show local AgentChute queue status."""
        from agentlint.agentchute.queue import queue_status

        status_data = queue_status()
        click.echo(f"Queue: {status_data['queue_path']}")
        click.echo(f"Pending: {status_data['pending']}")
        click.echo(f"Queued total: {status_data['queued']}")
        click.echo(f"Delivered cursor: {status_data['delivered_cursor']}")
        click.echo(f"Failures: {status_data['failures']}")

    @queue_group.command("flush")
    @click.option("--max-events", default=None, type=int, help="Maximum events to flush")
    @click.option("--batch-size", default=50, type=int, help="Maximum events per API batch")
    @click.option(
        "--time-budget", default=3.0, type=float, help="Maximum seconds to spend flushing"
    )
    def queue_flush_command(
        max_events: int | None,
        batch_size: int,
        time_budget: float,
    ) -> None:
        """Flush queued AgentChute events now."""
        from agentlint.cli import _flush_agentchute_queue

        _flush_agentchute_queue(
            max_events=max_events,
            batch_size=batch_size,
            time_budget=time_budget,
            dry_run=False,
            background=False,
        )

    @queue_group.command("discard-pending")
    @click.option("--yes", is_flag=True, help="Skip confirmation")
    def queue_discard_pending_command(yes: bool) -> None:
        """Mark pending AgentChute events delivered without uploading them."""
        from agentlint.agentchute.queue import mark_existing_events_delivered, queue_status

        status_data = queue_status()
        pending = int(status_data.get("pending", 0) or 0)
        if pending <= 0:
            click.echo("AgentChute queue: no pending events.")
            return
        if not yes and not click.confirm(
            f"Discard {pending} pending AgentChute event(s) without uploading?",
            default=False,
        ):
            click.echo("AgentChute queue unchanged.")
            return
        skipped = mark_existing_events_delivered()
        click.echo(
            f"AgentChute queue: discarded {skipped} pending event(s); "
            "future events will upload normally"
        )

    @queue_group.command("inspect")
    @click.option("--last", "last_n", default=5, type=int, help="Show the last N queued events")
    def queue_inspect(last_n: int) -> None:
        """Show privacy-safe queued event summaries."""
        from agentlint.agentchute.queue import _queue_path, _read_lines

        lines = _read_lines()
        if not lines:
            click.echo("Queue is empty.")
            return
        for raw in lines[-last_n:]:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                click.echo("poison line: invalid JSON")
                continue
            event = item.get("event") or {}
            click.echo(
                f"{item.get('line_offset', '?')}: {event.get('event', '?')} "
                f"{event.get('tool_name', '')} session={item.get('session_key', '')} "
                f"violations={len(event.get('violations') or [])}"
            )
        click.echo(f"Queue file: {_queue_path()}")
