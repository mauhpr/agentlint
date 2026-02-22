# Configuration Reference

AgentLint is configured via `agentlint.yml` (or `agentlint.yaml`, `.agentlint.yml`) in your project root. Run `agentlint init` to generate one with auto-detected defaults.

## Quick reference

```yaml
# All options with their defaults
stack: auto                    # auto | manual
severity: standard             # strict | standard | relaxed
packs:
  - universal                  # Always active
  # - python                   # Auto-detected from pyproject.toml / setup.py
  # - frontend                 # Auto-detected from package.json
  # - react                    # Auto-detected from react in dependencies
  # - seo                      # Auto-detected from SSR/SSG framework
  # - security                 # Opt-in: blocks Bash file writes, network exfiltration
# custom_rules_dir: .agentlint/rules/   # Path to custom rule files

rules:
  # === Universal pack ===
  no-secrets:        { enabled: true }                  # ERROR - blocks secrets in writes
  no-env-commit:     { enabled: true }                  # ERROR - blocks .env file writes
  no-force-push:     { enabled: true }                  # ERROR - blocks force-push to main
  no-destructive-commands: { enabled: true }             # WARNING - warns on rm -rf, DROP TABLE
  dependency-hygiene: { enabled: true }                  # WARNING - warns on ad-hoc pip/npm install
  max-file-size:     { enabled: true, limit: 500 }      # WARNING - warns on large files
  drift-detector:    { enabled: true, threshold: 10 }    # WARNING - warns on many edits without tests
  no-debug-artifacts: { enabled: true }                  # WARNING - detects leftover debug statements
  test-with-changes: { enabled: true }                   # WARNING - warns if no tests updated
  no-todo-left:      { enabled: true }                   # INFO - reports TODO/FIXME in changed files
  no-push-to-main:   { enabled: true }                   # WARNING - warns on direct push to main/master
  no-skip-hooks:     { enabled: true }                   # WARNING - warns on git commit --no-verify
  no-test-weakening: { enabled: true }                   # WARNING - warns on skipped tests, assert True
  # === Security pack (opt-in) ===
  # no-bash-file-write: { enabled: true }                # ERROR - blocks Bash file writes (cat >, tee, etc.)
  # no-network-exfil:   { enabled: true }                # ERROR - blocks potential data exfiltration
  # === Python pack ===
  # no-bare-except:    { enabled: true, allow_reraise: true }
  # no-unsafe-shell:   { enabled: true }
  # no-sql-injection:  { enabled: true }
  # === Frontend pack ===
  # a11y-image-alt:    { enabled: true }
  # mobile-touch-targets: { enabled: true }
  # === React pack ===
  # react-query-loading-state: { enabled: true }
  # === SEO pack ===
  # seo-page-metadata: { enabled: true }
```

## Top-level options

### `stack`

Controls how rule packs are activated.

- `auto` (default) — Detect from project files (pyproject.toml, package.json, etc.)
- Any other value — Use only the `universal` pack

### `severity`

Global severity mode. Transforms all violation severities:

| Mode | Effect |
|------|--------|
| `strict` | WARNING becomes ERROR, INFO becomes WARNING |
| `standard` | No transformation (default) |
| `relaxed` | WARNING becomes INFO |

### `packs`

Explicit list of rule packs to activate. Overrides auto-detection.

Available packs: `universal`, `python`, `frontend`, `react`, `seo`, `security`.

```yaml
packs:
  - universal
  - python
  - frontend
```

### `custom_rules_dir`

Path (relative to project root) containing custom rule `.py` files.

```yaml
custom_rules_dir: .agentlint/rules/
```

### `rules`

Per-rule configuration overrides. Each key is a rule ID.

```yaml
rules:
  no-secrets:
    enabled: false        # Disable the rule entirely
  max-file-size:
    limit: 300            # Override default (500)
  drift-detector:
    threshold: 5          # Override default (10)
```

## Universal rules reference

### `no-secrets` (PreToolUse, ERROR)

Blocks writes containing API keys, tokens, or passwords.

Detects patterns:
- Stripe keys (`sk_live_`, `sk_test_`)
- AWS keys (`AKIA...`)
- GitHub tokens (`ghp_`, `github_pat_`)
- Slack tokens (`xoxb-`, `xoxp-`)
- Generic API key assignments
- Bearer tokens and JWTs
- Password string assignments
- Private keys (RSA, EC, DSA)
- Database connection strings with credentials
- GCP service account files
- Terraform state files
- Sensitive filenames (`.npmrc`, `credentials.json`, etc.)
- Curl with authentication (`-u`, `-H "Authorization: ..."`)

**Config options:**
- `extra_prefixes` — Additional token prefixes to detect (e.g. `["myco_secret_"]`)

### `no-env-commit` (PreToolUse, ERROR)

Blocks writing `.env`, `.env.local`, `.env.production`, and similar credential files. Also detects Bash commands that write to `.env` files (e.g. `echo "SECRET=val" > .env`, `cp .env.example .env`, `tee .env`, `sed -i ... .env`).

### `no-force-push` (PreToolUse, ERROR)

Blocks `git push --force` or `git push -f` to `main` or `master` branches.

### `no-destructive-commands` (PreToolUse, WARNING/ERROR)

Warns on destructive shell commands. Some patterns escalate to ERROR severity:

**WARNING:**
- `rm -rf` (except safe targets like `node_modules`, `dist`, `__pycache__`)
- `DROP TABLE`, `DROP DATABASE`
- `git reset --hard`, `git clean -fd`
- `chmod 777` (overly permissive)
- `docker system prune -a --volumes`
- `kubectl delete namespace`

**ERROR (catastrophic):**
- `rm -rf /` or `rm -rf ~` (root/home deletion)
- `mkfs` (filesystem format)
- `dd if=/dev/zero` (disk wipe)
- Fork bombs
- `git branch -D main/master` (protected branch deletion)

### `dependency-hygiene` (PreToolUse, WARNING)

Warns on ad-hoc package installation:
- `pip install <package>` (but allows `pip install -e .`)
- `npm install <package>` (but allows `npm ci`, `npm install` with no args)

### `max-file-size` (PostToolUse, WARNING)

Warns when a written/edited file exceeds a line count threshold.

**Config options:**
- `limit` — Maximum lines (default: `500`)

### `drift-detector` (PostToolUse, WARNING)

Tracks file edits and test runs. Warns after N edits without running tests.

**Config options:**
- `threshold` — Edit count before warning (default: `10`)

### `no-debug-artifacts` (Stop, WARNING)

At session end, scans changed files for debug statements:
- JavaScript/TypeScript: `console.log()`, `debugger`
- Python: `print()`, `pdb.set_trace()`, `breakpoint()`

Skips test files.

### `test-with-changes` (Stop, WARNING)

At session end, warns if source files (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`) were changed but no test files were updated.

Skips migrations, configs, and settings files.

### `no-todo-left` (Stop, INFO)

At session end, reports any `TODO`, `FIXME`, `HACK`, or `XXX` comments found in changed files.

### `no-push-to-main` (PreToolUse, WARNING)

Warns on direct `git push` to `main` or `master` branches (excluding force pushes, which are handled by `no-force-push`).

### `no-skip-hooks` (PreToolUse, WARNING)

Warns when git commands use `--no-verify` or `--no-gpg-sign` flags to skip safety hooks.

### `no-test-weakening` (PreToolUse, WARNING)

Detects patterns that weaken test suites when writing to test files:
- Skip markers (`@pytest.mark.skip`, `@unittest.skip`, `it.skip()`, `describe.skip()`)
- Trivially passing assertions (`assert True`, `assertTrue(True)`, `expect(true).toBe(true)`)
- Commented-out assertions (`# assert ...`, `// expect(...)`)
- `@pytest.mark.xfail` without a reason
- Empty test functions (`def test_...: pass`)

## Security rules reference

The security pack is **opt-in** — add `security` to your `packs` list to enable it. These rules provide stricter enforcement for sensitive environments.

### `no-bash-file-write` (PreToolUse, ERROR)

Blocks file writes via Bash commands, enforcing use of the Write/Edit tools instead. Detects: `cat >`, `echo >`, `tee`, `sed -i`, `cp`, `mv`, `perl -pi`, `awk >`, `dd of=`, `python -c ... open(...).write()`, and heredocs.

**Config options:**
- `allow_paths` — Glob patterns for allowed write targets (e.g. `["*.log", "/tmp/*"]`)
- `allow_patterns` — Regex patterns for allowed commands (e.g. `["echo.*>>.*\\.log"]`)

### `no-network-exfil` (PreToolUse, ERROR)

Blocks potential data exfiltration via network commands. Detects: `curl POST/PUT` with data, `curl -d @file`, piping secrets to curl, `nc` with sensitive files, `scp` of credential files, `wget --post-file`, `python requests.post()`, and `rsync` of sensitive files to remote.

Default allowed hosts: `github.com`, `pypi.org`, `registry.npmjs.org`, `rubygems.org`.

**Config options:**
- `allowed_hosts` — Additional allowed destination hosts

## Python rules reference

### `no-bare-except` (PreToolUse, WARNING)

Prevents bare `except:` clauses that catch all exceptions including `SystemExit` and `KeyboardInterrupt`.

**Config options:**
- `allow_reraise` — Allow bare except if it contains a bare `raise` (default: `true`)

### `no-unsafe-shell` (PreToolUse, ERROR)

Blocks unsafe shell execution via `subprocess` with `shell=True` and `os` module shell functions.

**Config options:**
- `allow_shell_true` — Allow subprocess calls with `shell=True` (default: `false`)

### `no-dangerous-migration` (PreToolUse, WARNING)

Warns about dangerous database migration operations in Alembic migration files (dropping columns, renaming tables, etc.).

**Config options:**
- `migration_paths` — Custom path markers for migration files (default: detects `migration`, `alembic`, `versions` in path)
- `require_timezone` — Enforce `timezone=True` on DateTime columns (default: `true`)

### `no-wildcard-import` (PreToolUse, WARNING)

Prevents `from module import *` which pollutes the namespace and makes dependencies unclear.

**Config options:**
- `allow_in` — Files where wildcard imports are allowed (default: `["__init__.py"]`)

### `no-unnecessary-async` (PostToolUse, INFO)

Flags `async def` functions that never use `await`. Skips test files and stub/abstract implementations.

**Config options:**
- `ignore_decorators` — Additional decorator names to skip (default: merges with `property`, `override`, `abstractmethod`)

### `no-sql-injection` (PreToolUse, ERROR)

Blocks SQL queries built via string interpolation (f-strings, `.format()`, `%` operator, concatenation).

**Config options:**
- `extra_keywords` — Additional SQL keywords to detect beyond `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`

## Frontend rules reference

### `a11y-image-alt` (PreToolUse, WARNING)

Ensures images have `alt` text for screen readers (WCAG 1.1.1).

**Config options:**
- `extra_components` — Additional image component names beyond `img` and `Image`

### `a11y-form-labels` (PreToolUse, WARNING)

Ensures form inputs have associated `<label>` elements or `aria-label` attributes (WCAG 1.3.1).

### `a11y-interactive-elements` (PreToolUse, WARNING)

Ensures interactive elements have proper ARIA attributes. Detects link anti-patterns like "click here".

**Config options:**
- `link_anti_patterns` — Custom anti-pattern phrases (default: `click here`, `read more`, `learn more`, `here`)

### `a11y-heading-hierarchy` (PreToolUse, INFO)

Ensures proper heading hierarchy — no multiple `<h1>` elements and no skipped heading levels.

**Config options:**
- `max_h1` — Maximum number of `<h1>` elements per page (default: `1`)

### `mobile-touch-targets` (PreToolUse, WARNING)

Ensures interactive elements meet minimum touch target size of 44x44 CSS pixels (WCAG 2.5.5).

### `mobile-responsive-patterns` (PreToolUse, INFO)

Warns about desktop-only layout patterns: large grids without responsive breakpoints, fixed widths, and hover-only interactions.

**Config options:**
- `min_grid_cols_warning` — Minimum grid columns that trigger a warning (default: `4`)

### `style-no-arbitrary-values` (PreToolUse, INFO)

Warns about arbitrary Tailwind CSS values (e.g. `w-[347px]`, `text-[#1a2b3c]`) that bypass design tokens.

### `style-focus-visible` (PreToolUse, WARNING)

Ensures focus indicators (`outline`, `ring`) are not removed without replacement. Checks for `outline: none` or `outline-none` without a `focus-visible` or `focus:ring` alternative (WCAG 2.4.7).

## React rules reference

### `react-query-loading-state` (PreToolUse, WARNING)

Ensures `useQuery` / `useSuspenseQuery` results destructure and handle `isLoading` and `isError` (or `error`) states.

**Config options:**
- `hooks` — Custom query hook names (default: `useQuery`, `useSuspenseQuery`)

### `react-empty-state` (PreToolUse, INFO)

Suggests adding empty state handling when `array.map()` is used in JSX without a corresponding length/empty check.

### `react-lazy-loading` (PreToolUse, INFO)

Suggests `React.lazy()` for heavy components imported in page-level files. Ensures `<Suspense>` wraps lazy-loaded components.

**Config options:**
- `heavy_components` — Custom component names considered heavy (default: `Chart`, `DataTable`, `Editor`, `Calendar`, `Map`, `RichTextEditor`, `CodeEditor`, `Spreadsheet`)
- `page_patterns` — Custom path patterns for page files (default: `pages/`, `app/`, `routes/`)

## SEO rules reference

### `seo-page-metadata` (PreToolUse, WARNING)

Ensures page files include `<title>` and meta description. Detects framework-specific patterns (Next.js `generateMetadata`, Nuxt `useHead`, etc.).

**Config options:**
- `page_patterns` — Custom page path patterns (default: `pages/`, `app/`, `routes/`)
- `metadata_components` — Additional metadata component names

### `seo-open-graph` (PreToolUse, INFO)

Ensures pages that have metadata also include Open Graph (`og:`) tags for social media previews.

**Config options:**
- `required_properties` — Required OG properties (default: `og:title`, `og:description`, `og:image`)

### `seo-semantic-html` (PreToolUse, INFO)

Encourages semantic HTML elements (`<main>`, `<nav>`, `<article>`, `<section>`) over excessive `<div>` usage.

**Config options:**
- `min_div_threshold` — Minimum number of `<div>` elements before warning (default: `10`)

### `seo-structured-data` (PreToolUse, INFO)

Suggests adding JSON-LD structured data (`<script type="application/ld+json">`) to content pages.

**Config options:**
- `content_path_patterns` — Path patterns for content pages (default: `product`, `article`, `blog`, `post`, `recipe`, `event`)

## Full example

```yaml
stack: auto
severity: standard

packs:
  - universal
  # - python
  # - frontend
  # - react
  # - seo
  # - security          # Opt-in: blocks Bash file writes, network exfiltration

rules:
  # Universal
  no-secrets:
    enabled: true
    extra_prefixes: []        # Additional token prefixes to detect
  no-env-commit:
    enabled: true
  no-force-push:
    enabled: true
  no-push-to-main:
    enabled: true
  no-skip-hooks:
    enabled: true
  no-test-weakening:
    enabled: true
  no-destructive-commands:
    enabled: true
  dependency-hygiene:
    enabled: true
  max-file-size:
    limit: 500
  drift-detector:
    threshold: 10
  no-debug-artifacts:
    enabled: true
  test-with-changes:
    enabled: true
  no-todo-left:
    enabled: true

  # Security (opt-in)
  no-bash-file-write:
    allow_paths: []           # Glob patterns for allowed targets
    allow_patterns: []        # Regex patterns for allowed commands
  no-network-exfil:
    allowed_hosts: []         # Additional allowed hosts

  # Python
  no-bare-except:
    allow_reraise: true
  no-unsafe-shell:
    allow_shell_true: false
  no-dangerous-migration:
    require_timezone: true
  no-wildcard-import:
    allow_in: ["__init__.py"]
  no-sql-injection:
    enabled: true

  # Frontend
  a11y-image-alt:
    enabled: true
  a11y-heading-hierarchy:
    max_h1: 1
  mobile-responsive-patterns:
    min_grid_cols_warning: 4

  # React
  react-query-loading-state:
    enabled: true
  react-lazy-loading:
    heavy_components: ["Chart", "DataTable", "Editor"]

  # SEO
  seo-page-metadata:
    enabled: true
  seo-semantic-html:
    min_div_threshold: 10
  seo-structured-data:
    content_path_patterns: ["product", "article", "blog"]

# custom_rules_dir: .agentlint/rules/
```
