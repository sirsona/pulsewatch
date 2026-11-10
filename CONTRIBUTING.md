# Contributing

Thanks for taking a look at PulseWatch. This is a small portfolio project, but it
is maintained with production habits: typed code, tests for behaviour, and
reviewable changes.

## Development setup

Requirements: Linux, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/sirsona/pulsewatch.git
cd pulsewatch
uv sync
cp .env.example .env
uv run pulsewatch --reload
```

Run the full quality gate before opening a pull request:

```bash
make check
```

That runs:

- `ruff format --check .`
- `ruff check .`
- `mypy src tests`
- `pytest` with branch coverage and an 85% floor

## Guidelines

### Code

- Keep HTTP contracts in Pydantic models under `src/pulsewatch/api/schemas.py`.
- Keep blocking system calls out of the event loop. Synchronous route handlers
  are fine; FastAPI runs them in a threadpool.
- Raise typed exceptions for expected failures and let unexpected exceptions
  reach the middleware boundary.
- Do not log secrets, request bodies, or arbitrary query strings.
- Add a module docstring and type annotations to new modules.

### Tests

- Every behaviour change needs a test that would fail without it.
- Prefer dependency injection (`create_app(settings=..., collector=...)`) over
  patching module globals.
- Use `tmp_path` for filesystem-dependent settings.
- Keep tests deterministic; mock psutil at its call boundary for collector
  tests.
- Do not lower the coverage threshold to make a change pass.

### Commits and pull requests

- Use focused, imperative commit subjects, for example:
  `feat(api): add history endpoint`.
- Conventional prefixes are preferred: `feat`, `fix`, `docs`, `test`, `refactor`,
  `build`, `ci`, `chore`.
- Describe the user-visible behaviour and any operational impact in the PR.
- Update the README, API docs, or deployment docs when a contract or operational
  procedure changes.
- Keep the PR free of credentials, environment files, and generated local data.

### Definition of done

- [ ] Tests cover the new behaviour and the full suite passes.
- [ ] Ruff formatting and linting pass.
- [ ] mypy passes for `src` and `tests`.
- [ ] Public API or configuration changes are documented.
- [ ] Deployment-sensitive changes are reflected in `docs/deployment.md`.
- [ ] CI is green.

## Reporting bugs and security issues

Use the GitHub issue templates for bugs and feature requests. For vulnerabilities,
follow [SECURITY.md](SECURITY.md) and do not open a public issue.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
