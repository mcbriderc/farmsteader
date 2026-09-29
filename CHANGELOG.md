# Changelog

All notable changes to FarmSteader are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release tooling depends on the shape of this file: `scripts/release.sh` moves
the `## [Unreleased]` block into a new version section, and the release workflow
both asserts that a `## [X.Y.Z]` heading exists for the tag being built and
extracts that section as the published release notes. Keep the headings in the
`## [X.Y.Z] - YYYY-MM-DD` form.

## [Unreleased]

## [0.4.0] - 2026-09-28

### Added

- **Proxmox VE installer.** From a Proxmox VE 8 or 9 node's shell, one command
  creates an unprivileged Debian 13 container and installs FarmSteader in it,
  with default settings or an advanced menu (size, storage, static IP, VLAN,
  admin account and more). Running it again offers to update an existing
  FarmSteader container, using that install's own rollback-safe updater. It can
  also run unattended with every setting preset in the environment.

## [0.3.0] - 2026-09-28

### Added

- **One-command server install.** `deploy/install.sh` installs FarmSteader on
  a fresh Debian 13 or Ubuntu machine, container or VM: PostgreSQL + PostGIS,
  Redis, nginx and the app, with an admin account and nightly database backups.
  It downloads a published release, verifies its checksum, and only reports
  success once the site answers with the version it installed.
- **In-place upgrades with automatic rollback.** `deploy/update.sh` upgrades to
  a newer release, taking a database dump first. If migrations fail or the new
  version does not come up healthy, the previous release and the database are
  restored automatically. Configuration and uploaded files are never touched.

### Changed

- Each release is installed in its own directory with its own Python
  environment, and the running version is switched with a single symlink, so
  an upgrade can be undone exactly.
- Web and background-worker counts are sized from the machine's memory instead
  of its CPU count, which inside a container could be the host's and start
  enough processes to exhaust memory.

### Fixed

- Restarting or stopping the background worker no longer takes the website
  down (the services shared a runtime directory, and stopping one deleted the
  web server's socket).
- The scheduler keeps its record of when tasks last ran across reboots, so
  daily tasks no longer re-run after a restart.
- A fresh install no longer fails to create the PostGIS extension, and
  generated database passwords can no longer break the database URL.

### Removed

- `deploy/incus/setup.sh`, replaced by `deploy/install.sh`.

## [0.2.1] - 2026-09-28

### Changed

- The provisioning script sets `FARMSTEADER_SOURCE_URL` to the public
  repository, `https://github.com/mcbriderc/farmsteader`, so a fresh install
  shows the sidebar "Source" link. The setting still defaults to empty.
- The public GitHub repository now receives one source snapshot per release
  instead of the full development history. Development continues on the
  private Forgejo instance; GitHub carries each release's source and
  downloadable artifacts.

## [0.2.0] - 2026-09-28

First release with a deployable story. Everything before this was
checkout-and-run-it-yourself.

### Added

- Whole-farm backup and restore: a zip of `manifest.json` + `data.json` +
  `media/`, exposed in the UI and as `manage.py farm_backup` / `farm_restore`.
  Restore always creates a *new* farm, so it can never overwrite live data.
- Dark mode, toggled from the sidebar and remembered per browser. Driven by a
  `dark` class on `<html>` that a blocking script in `<head>` sets before first
  paint, so there is no flash of light theme on load.
- `/healthz` (liveness) and `/readyz` (database and Redis readiness, `503` when
  degraded) JSON endpoints, both unauthenticated and reporting the app version.
- `config/__version__.py` as the single source of truth for the version,
  available as `settings.APP_VERSION`.
- Optional Sentry error reporting, entirely opt-in via `SENTRY_DSN`.
- `scripts/build-css.sh`, which compiles the stylesheet by driving the pinned
  standalone Tailwind binary directly, with an upstream checksum verified before
  the binary is ever executed.
- Continuous integration on Forgejo Actions, including a SonarQube scan and a
  `manage.py check --deploy` gate on production settings.
- FarmSteader is now licensed under the GNU Affero General Public License v3.0.
  Adds `LICENSE`, `THIRD-PARTY-NOTICES.md` for the vendored browser libraries,
  and `CONTRIBUTING.md` + `CLA.md` for contributors.
- `FARMSTEADER_SOURCE_URL` setting, which renders a "Source" link and the
  version in the sidebar footer (AGPL section 13). Unset by default.
- Crop Records page (`/crops/records/`), listing every planting across all
  fields with filters for season, status, and crop or variety. Plantings were
  previously visible only on the field they belonged to, so a crop seeded on a
  field did not appear anywhere in the Crops section.

### Fixed

- **A fresh production install now works.** Previously every request
  infinite-redirected: `SECURE_SSL_REDIRECT` was hardcoded on while nginx listens
  on HTTP only, with no `SECURE_PROXY_SSL_HEADER`. TLS is now one
  `FARMSTEADER_HTTPS` switch, defaulting off for plain-HTTP LAN installs.
- **Production could silently run development settings.** `config/celery.py`
  defaulted `DJANGO_SETTINGS_MODULE` to dev and, being imported eagerly by
  `config/__init__.py`, won over the value in `wsgi.py` -- so a process started
  without the variable came up with `DEBUG=True` and `ALLOWED_HOSTS=["*"]`
  instead of refusing to boot. All production entrypoints now default to prod.
- `sync_commodity_prices` failed on every scheduled run: `yfinance` was imported
  but declared in no requirements file.
- Cross-farm data leaks in CSV/XLSX import: row matching and foreign-key lookups
  by name are now confined to the importing farm.
- Unauthenticated requests could reach farm-scoped pages.
- SoilGrids sync used invalid depth ranges and did not handle timeouts.
- The deployment shipped with no CSS, because `static/css/dist/` is git-ignored
  and the provisioning script never ran a Tailwind build.
- Dark mode: dropdown option lists were drawn on the browser's white default
  with near-white text, making them unreadable. Tailwind's preflight resets
  every form control to a transparent background, which is the one case
  `color-scheme: dark` cannot correct, so selects, text inputs and textareas now
  carry an explicit themed surface.
- Stylesheet changes no longer go unnoticed by an already-open browser tab. The
  link now carries a `?v=<mtime>` stamp, so a rebuilt stylesheet is a different
  URL and cannot be served from a stale cache entry.
- `collectstatic` no longer publishes the Tailwind source CSS: it has moved to
  `assets/css/input.css`, outside the static files directories.

### Changed

- Every view declares its permitted HTTP methods (SonarQube `python:S3752`).
- `STATIC_ROOT` and `MEDIA_ROOT` are env-overridable, so an upgrade can replace
  the application directory wholesale without destroying uploads.
- Persistent database connections in production, with health checks so a
  restarted PostgreSQL cannot poison live workers.
- Static files are served through WhiteNoise when no reverse proxy is in front.
- The Tailwind CLI version is pinned rather than tracking `latest`, so an
  upstream release cannot change the compiled output without a commit.
- Python dependencies are locked. `requirements/*.in` hold the direct
  dependencies as ranges, each with a major-version ceiling, and
  `requirements/*.txt` are compiled exact pins (transitives included) generated
  by the new `scripts/lock-deps.sh` under Python 3.13. CI, releases and every
  install now get the same versions; previously each requirement was an
  unbounded `>=` and resolved to whatever was newest on the day. The locked
  stack includes Django 6.1, redis-py 8 and django-debug-toolbar 8, so an
  existing development venv should run `pip install -r requirements/dev.txt`.

[Unreleased]: https://github.com/mcbriderc/farmsteader/compare/v0.4.0...HEAD
[0.2.1]: https://github.com/mcbriderc/farmsteader/releases/tag/v0.2.1
[0.3.0]: https://github.com/mcbriderc/farmsteader/releases/tag/v0.3.0
[0.4.0]: https://github.com/mcbriderc/farmsteader/releases/tag/v0.4.0
