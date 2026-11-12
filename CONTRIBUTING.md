# Contributing

Thanks for taking a look at PulseWatch. This is a small portfolio project, but it
is maintained with production habits: typed code, tests for behaviour, and
reviewable changes.

## Development setup

Requirements: Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/), and
PostgreSQL 15+.

```bash
git clone https://github.com/sirsona/pulsewatch.git
cd pulsewatch
uv sync
cp .env.example .env

# Update PULSEWATCH_DATABASE_URL if needed.
make run
```

`make run` applies Alembic migrations before starting the reload server. If you
invoke the CLI directly, run `uv run alembic upgrade head` first.

For an integration-test database:

```bash
createdb pulsewatch_test
export PULSEWATCH_DATABASE_URL=postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch_test
export PULSEWATCH_TEST_DATABASE_URL=$PULSEWATCH_DATABASE_URL
uv run alembic upgrade head
uv run pytest -m integration
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
- `scripts/verify-systemd-unit.sh`

## Guidelines

### Code

- Keep HTTP contracts in Pydantic models under `src/pulsewatch/api/schemas.py`.
- Keep blocking system calls out of the event loop. Use `asyncio.to_thread` for
  blocking work such as psutil collection.
- Keep psutil collection in the sampler; API routes should read persisted state.
- Raise typed exceptions for expected failures and let unexpected exceptions
  reach the middleware boundary.
- Do not log secrets, database URLs, request bodies, or arbitrary query strings.
- Add a module docstring and type annotations to new modules.
- Schema changes require a new Alembic migration; never edit an applied one.

### Tests

- Every behaviour change needs a test that would fail without it.
- Prefer dependency injection
  (`create_app(settings=..., collector=..., repository=...)`) over patching module
  globals.
- Use `tmp_path` for filesystem-dependent settings.
- Keep tests deterministic; mock psutil at its call boundary for collector
  tests.
- Repository tests use SQLite for speed; PostgreSQL integration tests are marked
  with `@pytest.mark.integration` and run when `PULSEWATCH_TEST_DATABASE_URL` is
  set.
- Use injected clocks for retention tests instead of sleeping.
- Test cursor boundaries, malformed cursors, and same-timestamp ordering.
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
- [ ] Database changes include a migration and integration coverage.
- [ ] New background service loops have start/stop and failure-path tests.
- [ ] Deployment-sensitive changes are reflected in `docs/deployment.md`.
- [ ] CI is green.

## Reporting bugs and security issues

Use the GitHub issue templates for bugs and feature requests. For vulnerabilities,
follow [SECURITY.md](SECURITY.md) and do not open a public issue.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
