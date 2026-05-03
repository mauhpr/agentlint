# Setup Guide: Generic HTTP/Webhook

AgentLint can be integrated with any agent framework via HTTP/webhook.

## Configuration

Add to `agentlint.yml`:

```yaml
generic:
  webhook_url: https://your-ci.example.com/agentlint
  headers:
    Authorization: Bearer ${TOKEN}
```

## API

### POST /check

Request:
```json
{
  "event": "pre_tool_use",
  "tool_name": "file_write",
  "tool_input": {
    "file_path": "config.py",
    "content": "API_KEY = 'secret'"
  }
}
```

Response:
```json
{
  "blocked": true,
  "violations": [
    {
      "rule_id": "no-secrets",
      "message": "Possible secret detected: API key pattern",
      "severity": "error"
    }
  ]
}
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AGENTLINT_PROJECT_DIR` | Project directory |
| `AGENTLINT_SESSION_ID` | Session ID |

## Custom Integration

```python
from agentlint.adapters.generic import GenericAdapter
from agentlint.config import load_config
from agentlint.engine import Engine

adapter = GenericAdapter()
project_dir = adapter.resolve_project_dir()
config = load_config(project_dir)
rules = load_rules(config.packs)
engine = Engine(config=config, rules=rules)

context = adapter.build_rule_context(
    event=adapter.translate_event("pre_tool_use"),
    raw_payload={"tool_name": "write", "tool_input": {...}},
    project_dir=project_dir,
    session_state={},
)
result = engine.evaluate(context)
```
