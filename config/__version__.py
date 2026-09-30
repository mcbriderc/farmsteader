"""Single source of truth for the application version.

A plain module rather than `pyproject.toml`: there is no `[build-system]` table,
so the project is never installed as a distribution and
`importlib.metadata.version("farmsteader")` raises `PackageNotFoundError` at
runtime. This module is importable from settings and greppable from shell
without a TOML parser, which is what the release tooling needs:

    sed -n 's/^__version__ = "\\(.*\\)"$/\\1/p' config/__version__.py

Keep the assignment on one line and in that exact form -- the CI release gate
parses it with the expression above and fails the build when it disagrees with
the git tag.
"""

__version__ = "0.5.0"
