# Contributing

This is a personal project with a defined roadmap and limited review time.
Small fixes, tests and documentation changes are welcome. For larger changes,
please open an issue first so we can agree on the approach before you spend
time on a PR.

## Before you start

- Check [PLAN.md](PLAN.md). Features that are not on the roadmap need a
  maintainer to agree to them first.
- For a bug, test or documentation fix, you can open a PR directly. Link an
  existing issue if there is one.
- For a feature or refactor, open an issue and wait for a reply before starting.
- Unrelated changes, drive-by refactors and PRs that ignore this guide may be
  closed without review.

## Pull requests

- Keep one concern per PR.
- Link the issue or PLAN item (`T-xx` or `B-xx`) in the description.
- Follow the layout and conventions in
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
  [docs/TESTING.md](docs/TESTING.md) and [SECURITY.md](SECURITY.md).
- Add tests for behavior changes and update the relevant documentation.
- Keep the diff focused. Do not mix in unrelated cleanups or formatting
  changes.
- Run the checks below before opening the PR.

### Backend

```bash
pip install -r requirements-dev.txt
python -m py_compile backend/*.py backend/routes/*.py
python -m pytest -q
```

### Frontend

```bash
cd frontend
npm ci
npm test
npm run lint
npm run format:check
npm run check
npm run build
```

The container build is described in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## AI-assisted contributions

AI tools are allowed, but you are responsible for the change. You should
understand the code, be able to explain the design decisions, and answer
review questions. If AI did a substantial part of the work, say so in the PR
description. PRs that look like unreviewed generated output, or that cannot
answer basic questions about the change, may be closed.

## Review and maintenance

- Maintainers decide whether a change fits the roadmap. Not every PR will be
  merged.
- You are expected to respond to review comments on your PR. You are not
  expected to maintain the feature after it is merged; the maintainers own
  merged code.
- If a PR is closed, you can open an issue to discuss the use case. A closed
  PR is not a judgment on the work itself.

## Security

Please do not report vulnerabilities in public issues. See
[SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contribution is licensed under the
AGPLv3, the same license as this project.
