# Contributing to FarmSteader

Thanks for wanting to help. Two things to know before you open a pull request.

## Licence

FarmSteader is licensed under the **GNU Affero General Public License v3.0**
(`LICENSE`). In short: you may run it, read it, change it and pass it on, but if
you run a *modified* copy as a network service, the people using that service
are entitled to your changes.

## Contributor Licence Agreement

**Every contribution requires a signed CLA** — see [`CLA.md`](CLA.md). It is
short, and it does not take your copyright away: you keep it, and you grant the
project a licence broad enough to relicense your contribution alongside the rest
of the codebase.

This is asked for honestly rather than quietly. Without it, the licence of this
project can never change again without tracking down every past contributor,
which in practice means it can never change. The realistic future uses are a
commercial licence for organisations whose policies forbid the AGPL, and a
hosted version. Neither is possible if the copyright is scattered.

If that is not something you want to sign, that is a legitimate position — open
an issue describing the change instead, and it can be implemented separately.

To sign: add your name and the date to the bottom of `CLA.md` in your first pull
request, and sign your commits off with `git commit -s`.

## Before you open a PR

The repository has a few invariants that are enforced by tests rather than by
review, and the guidance for working in this codebase lives in `CLAUDE.md`.
Worth reading the relevant section before changing theming, settings, or the
release scripts.

```bash
pytest                       # full suite, with coverage
pytest --no-cov              # faster
```

CI additionally runs, and a PR must pass, both of these:

```bash
scripts/ci/test.sh           # Tailwind build + pytest + `check --deploy`
shellcheck -x scripts/*.sh   # all shell must be shellcheck-clean
```

Two specifics that catch people out:

- **Views must declare their allowed HTTP methods** (`@require_GET`,
  `@require_POST`, `@require_http_methods`). SonarQube rule `python:S3752`
  flags any view without one.
- **Colour classes are semantic, not literal.** `text-gray-900` means "primary
  text" and renders near-white in dark mode. Never pick a stock Tailwind colour
  expecting a fixed value — `tests/test_theming.py` will fail the build.

## Reporting something instead

Bug reports and feature requests need no CLA. Include the FarmSteader version
(shown in Settings, and in `/healthz`), how it was installed (LXC, container,
bare metal), and what you expected to happen.
