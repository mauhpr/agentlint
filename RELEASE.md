# AgentLint release process

This repo publishes the `agentlint` Python package to PyPI from GitHub Actions.
Do not publish from a local machine.

## Release owner checklist

1. Merge all required product/API/dashboard dependencies first.
   - If the release depends on AgentChute server behavior, merge and deploy
     AgentChute before publishing AgentLint.

2. Prepare a release PR from a branch like `release/vX.Y.Z-description`.
   Update these files together:
   - `pyproject.toml`
   - `src/agentlint/__init__.py`
   - `uv.lock`
   - `CHANGELOG.md`

3. Run local verification before opening or updating the PR.

   ```bash
   .venv/bin/pytest tests/test_cli.py tests/test_agentchute_policy_queue_sync.py -k "not test_list_rules_universal_pack"
   uv run ruff check CHANGELOG.md pyproject.toml src/agentlint/__init__.py src/agentlint/cli.py src/agentlint/agentchute/queue.py tests/test_cli.py tests/test_agentchute_policy_queue_sync.py
   ```

   Adjust the test list when the release touches other areas.

4. Open the PR and wait for required GitHub checks.
   - Python matrix must pass.
   - Codecov patch must pass.
   - Resolve conflicts by merging `origin/main` into the release branch.

5. Merge the PR into `main`.

6. Create the GitHub Release from the final `main` commit.

   ```bash
   git fetch origin main --tags
   TARGET_SHA="$(git rev-parse origin/main)"
   gh release create vX.Y.Z \
     --target "$TARGET_SHA" \
     --title "AgentLint vX.Y.Z" \
     --notes-file /path/to/release-notes.md
   ```

   `gh-personal` can be used instead of `gh` on machines configured with that
   wrapper.

7. Let GitHub Actions publish to PyPI.
   - The workflow is `.github/workflows/publish.yml`.
   - It runs on `release.published`.
   - It builds with `uv build`.
   - It publishes with trusted publishing through `pypa/gh-action-pypi-publish`.

   Check it with:

   ```bash
   gh run list --limit 5
   ```

8. Verify the package after the publish workflow succeeds.

   ```bash
   uv tool install --upgrade --reinstall agentlint
   agentlint --version
   ```

   Expected output:

   ```text
   agentlint X.Y.Z
   ```

## Important rules

- Do not run `uv publish` locally. PyPI credentials are intentionally owned by
  GitHub trusted publishing.
- Do not move an already published release tag. If a release is wrong after
  publishing, create a follow-up patch version.
- Keep release notes focused on user-visible behavior, fixes, and migration
  notes.
- If the release changes AgentLint behavior consumed by `agentlint-plugin`,
  release AgentLint first, verify PyPI, then release the plugin.
