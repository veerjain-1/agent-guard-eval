# Contributing to AgentGuard

Bug fixes, evaluator improvements, adapters, reports, tests, and documentation
are welcome. Start with an existing issue or open one describing the behavior
you want to change.

## Choose work

Search open issues **and pull requests** before starting so you can build on
existing work. Comment on an issue when you plan to take it on. Issues labeled
`good first issue` or `help wanted` include scoped contribution opportunities.
For larger features or new dependencies, discuss the approach in an issue first.

Bug reports should include a minimal trace or command, expected and actual
behavior, the AgentGuard/Python versions, and relevant output. Use synthetic
traces and placeholder credentials instead of production data.

## Local setup

Use Python 3.10 or newer. Fork the repository, clone your fork, and create a
branch from the latest `main`. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]" ruff
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.
Editable installation makes the `agentguard` command use your source changes.
The deterministic test suite needs no model credentials or live LLM calls.

## Validate your change

Run both lint and tests before submitting; passing tests alone does not check
lint rules:

```bash
ruff check .
pytest -q
git diff --check
```

For a focused CLI change, `pytest tests/test_cli.py -q` is a useful first pass;
run the full suite before submitting. For a bug fix, add a regression test that
fails on the original behavior and passes with the fix. Test failure paths and
exit codes when changing CLI error handling. Use deterministic fixtures or
mocked failures rather than external services or machine-specific permissions.

You can also smoke-test evaluation with the bundled sample:

```bash
agentguard evaluate examples/trace_valid.json -s examples/tool_schemas.json
```

CI runs lint, tests, and sample evaluation on Python 3.10, 3.11, and 3.12. Its
Python 3.12 job also builds and smoke-tests the Docker image; Docker is optional
for routine local Python changes. See [the workflow](.github/workflows/ci.yml)
for the current commands.

## Submit a pull request

Target `main` and keep the diff focused. Describe the concrete problem, resulting
behavior, linked issue (`Fixes #<number>` when appropriate), and the exact checks
you ran. Mention checks you could not run. Update usage examples if behavior
changes, and avoid unrelated formatting or dependency updates.

Respond to review feedback on the same PR. First-time fork contributions may
wait for a maintainer to authorize their CI run; that pending state is not a
test failure. Keep contributor authorship intact when building on someone
else's work.
