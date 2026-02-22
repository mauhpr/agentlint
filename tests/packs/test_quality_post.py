"""Tests for quality pack PostToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.quality.no_dead_imports import NoDeadImports


def _ctx(
    tool_name: str = "Write",
    tool_input: dict | None = None,
    config: dict | None = None,
    file_content: str | None = None,
) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input or {},
        project_dir="/tmp/project",
        config=config or {},
        file_content=file_content,
    )


class TestNoDeadImports:
    rule = NoDeadImports()

    def test_detects_unused_python_import(self):
        content = "import os\nimport sys\n\nprint('hello')\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "os" in violations[0].message
        assert "sys" in violations[0].message

    def test_allows_used_python_import(self):
        content = "import os\n\npath = os.path.join('a', 'b')\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_detects_unused_from_import(self):
        content = "from pathlib import Path\n\nprint('hello')\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Path" in violations[0].message

    def test_allows_used_from_import(self):
        content = "from pathlib import Path\n\np = Path('.')\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_handles_alias_imports(self):
        content = "import numpy as np\n\narr = np.array([1, 2, 3])\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_detects_unused_alias_import(self):
        content = "import numpy as np\n\nprint('hello')\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "np" in violations[0].message

    def test_skips_init_py(self):
        content = "from pathlib import Path\n\nprint('hello')\n"
        ctx = _ctx(
            tool_input={"file_path": "__init__.py"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_index_ts(self):
        content = "import { Foo } from './foo';\n\nconsole.log('hello');\n"
        ctx = _ctx(
            tool_input={"file_path": "index.ts"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_detects_unused_js_import(self):
        content = "import { useState, useEffect } from 'react';\n\nconst App = () => <div />;\n"
        ctx = _ctx(
            tool_input={"file_path": "app.tsx"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "useState" in violations[0].message
        assert "useEffect" in violations[0].message

    def test_allows_used_js_import(self):
        content = "import { useState } from 'react';\n\nconst [count] = useState(0);\n"
        ctx = _ctx(
            tool_input={"file_path": "app.tsx"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_detects_unused_default_import(self):
        content = "import React from 'react';\n\nconst App = () => <div />;\n"
        ctx = _ctx(
            tool_input={"file_path": "app.jsx"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "React" in violations[0].message

    def test_allows_used_default_import(self):
        content = "import React from 'react';\n\nconst el = React.createElement('div');\n"
        ctx = _ctx(
            tool_input={"file_path": "app.jsx"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_non_code_files(self):
        content = "import something\n\nsome text\n"
        ctx = _ctx(
            tool_input={"file_path": "README.md"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_non_file_tools(self):
        ctx = _ctx(
            tool_name="Bash",
            tool_input={"command": "echo hi"},
            file_content="import os\n",
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_empty_content(self):
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=None,
        )
        assert self.rule.evaluate(ctx) == []

    def test_custom_ignore_files(self):
        content = "from pathlib import Path\n\nprint('hello')\n"
        ctx = _ctx(
            tool_input={"file_path": "exports.py"},
            file_content=content,
            config={"no-dead-imports": {"ignore_files": ["exports.py"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_underscore_prefixed_names(self):
        """Private imports (convention: unused but for side effects) are ignored."""
        content = "from typing import _SpecialForm\n\ndef foo(): pass\n"
        ctx = _ctx(
            tool_input={"file_path": "app.py"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_js_alias_import(self):
        content = "import { Foo as Bar } from './foo';\n\nconst x = Bar();\n"
        ctx = _ctx(
            tool_input={"file_path": "app.ts"},
            file_content=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_js_unused_alias_import(self):
        content = "import { Foo as Bar } from './foo';\n\nconsole.log('hello');\n"
        ctx = _ctx(
            tool_input={"file_path": "app.ts"},
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Bar" in violations[0].message
