# FarmSteader

A comprehensive, self-hosted farm management web application built with Django, PostgreSQL/PostGIS, and Celery. Designed for small-to-medium farms, FarmSteader tracks everything from field boundaries and livestock to equipment maintenance and produce -- all from a mobile-friendly browser interface.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Application Modules](#application-modules)
- [Data Model Reference](#data-model-reference)
- [External API Integrations](#external-api-integrations)
- [Getting Started (Development)](#getting-started-development)
- [Running the Application](#running-the-application)
- [Installing on a Server (Debian, Ubuntu, LXC or VM)](#installing-on-a-server-debian-ubuntu-lxc-or-vm)
- [Project Structure](#project-structure)
- [Configuration Reference](#configuration-reference)
- [Import / Export](#import--export)
- [Backup & Restore](#backup--restore)
- [Celery Tasks & Scheduling](#celery-tasks--scheduling)
- [Releases](#releases)

---

## Overview

FarmSteader provides a unified platform for managing all aspects of farm operations:

- **Land & Fields** -- Draw field boundaries and property lines on a map, auto-calculate acreage, see how much of each property is in fields, track crop rotations, and sync weather and soil data from public APIs.
- **Livestock** -- Ear tag registry, species/breed tracking, breeding lineage (sire/dam), veterinary records, immunization schedules, field-to-field movement history with days-in-field tracking, and feed inventory management with full feed type CRUD (pre-seeded with 29 common feed types) and per-animal feeding logs.
- **Crops** -- Global crop type catalog with USDA commodity codes and full CRUD management (pre-seeded with 19 common US crop types), harvest records with yield/quality/revenue, and daily market price sync from USDA NASS.
- **Equipment** -- Track tractors, implements, and vehicles with hour meters, maintenance logs, and next-service scheduling.
- **Buildings** -- Map building locations (barns, sheds, greenhouses), track assessed values, insurance, property taxes, and maintenance.
- **Consumables** -- Inventory management for feed, seed, fuel, chemicals, and medical supplies with reorder alerts, transaction history, and full consumable type CRUD (pre-seeded with 34 common types).
- **Employment** -- Employee directory, task kanban board with priorities and assignments, and time entry tracking.
- **Produce** -- Track farm produce from source to consumption with linkage to specific animals or crops, storage type, expiry alerts, and consumption/sale/donation/waste logging.
- **Data I/O** -- CSV and XLSX import/export for every data type with dry-run validation and preview.

The application is multi-tenant: a single installation supports multiple farms, each with its own isolated data. Users can belong to multiple farms with role-based access (owner, manager, worker, viewer).

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Django 5.2 LTS | ORM, auth, admin, templating, GeoDjango |
| Database | PostgreSQL 16 + PostGIS 3 | Relational storage with geospatial support |
| Task Queue | Celery 5.5 + Redis 7 | Background weather/soil/price sync |
| Frontend JS | HTMX + Alpine.js | Dynamic UI without a SPA framework (~75 KB total) |
| Maps | Leaflet.js + Leaflet Draw + Turf.js | Interactive field polygon drawing and area preview |
| CSS | Tailwind CSS (standalone CLI) | Utility-first responsive styling, no Node.js needed |
| HTTP Client | httpx | Async-capable HTTP for external API calls |
| Import/Export | django-import-export + openpyxl | CSV and XLSX for all models |
| Images | Pillow | Photo uploads for animals, equipment, buildings |
| Config | django-environ | Environment variable parsing from `.env` files |

---

## Architecture

### Multi-Tenancy

Every domain model inherits from `FarmOwnedModel`, which provides a foreign key to `Farm` plus `created_at` and `updated_at` timestamps. A `CurrentFarmMiddleware` reads the active farm from the user's session and attaches it to `request.farm`. Views use a `FarmAccessMixin` (for class-based views) or manual filtering (for function-based views) to scope all queries to the active farm. When creating records, the farm is auto-set from the request.

The only models *not* scoped to a farm are global catalogs: `CropType`, `ConsumableType`, `FeedType`, `MarketPrice`, `CommodityPrice`, and `WeatherCache`.

### Request Flow

```
Browser
  -> Nginx (static/media files, reverse proxy)
  -> Gunicorn (WSGI, multiple workers)
  -> Django Middleware Stack
     -> CurrentFarmMiddleware (sets request.farm)
     -> View (filters queryset by farm, renders template)
  -> Response
```

Every view declares the HTTP methods it accepts with `django.views.decorators.http`:
read-only pages use `@require_GET`, pages that both render and accept a form use
`@require_http_methods(["GET", "POST"])`, and action-only endpoints use `@require_POST`.
Anything else gets a 405 before the view body runs.

### Background Processing

```
Django View (on field save)
  -> celery.delay() (sends task to Redis)
  -> Celery Worker (picks up task)
     -> Open-Meteo API (weather)
     -> SoilGrids API (soil properties)
     -> USDA NASS API (crop prices)
  -> Database (stores cached results)
```

### Frontend Pattern

Pages are server-rendered Django templates styled with Tailwind CSS. Interactive elements (sidebar toggle, toast auto-dismiss, task status updates) use Alpine.js for local state and HTMX for server-driven partial updates. Maps use Leaflet.js with the Leaflet Draw plugin for polygon and point editing. Turf.js provides client-side acreage preview before form submission.

### Dark Mode

Every page supports a dark and a light theme. The toggle sits at the bottom of
the sidebar ("Light Mode" / "Dark Mode"), and in the top-right corner on the
login, register, and farm-select pages.

On a first visit the theme follows your operating system's appearance setting.
Once you pick one explicitly, that choice wins and is remembered.

The button names the theme it will switch you to, so in dark mode it reads
"Light Mode".

The preference is stored in the browser, not in your account — so it is per
device and per browser, and it applies to every farm you belong to. Clearing
site data resets it to following the OS.

Map imagery stays light in both themes — the controls, popups, and drawing
tools darken, but the tiles themselves are unchanged, so field boundaries and
terrain read the same way you are used to.

Map tiles stay light in both themes; the surrounding popups, zoom controls, and
drawing toolbar follow the theme.

Form controls follow the theme as well, including the list a dropdown opens —
in dark mode that list is dark with light text, not the browser's default white.

---

## Licence

FarmSteader is free software under the **GNU Affero General Public License,
version 3** — see `LICENSE`. You may run it, study it, change it and share it.

The one obligation worth knowing: if you **modify** FarmSteader and run it as a
service other people use over a network, those people are entitled to your
modified source. Running an unmodified copy — which is what almost every install
is — places no obligation on you at all, and using it on your own farm never
does.

Set `FARMSTEADER_SOURCE_URL` in `.env` to add a **Source** link to the sidebar
footer. If you have modified FarmSteader, point it at your fork; that link is
the simplest way to meet the obligation above. For an unmodified install, the
upstream repository is `https://github.com/mcbriderc/farmsteader`, and the
provisioning script writes that value for you. The setting itself defaults to
empty on purpose, so a modified copy never silently claims upstream as its source.

FarmSteader also includes third-party components (Leaflet, Leaflet.draw, htmx,
Alpine.js, Turf.js, Tailwind CSS) under their own MIT, BSD and 0BSD licences,
reproduced in `THIRD-PARTY-NOTICES.md`.

---

## Application Modules

### Accounts (`/accounts/`)

User authentication and farm management. Uses a custom `FarmUser` model extending Django's `AbstractUser`. Each user can create or join multiple farms through `FarmMembership` with roles: **owner**, **manager**, **worker**, or **viewer**.

**Key pages:** Login, Register (creates a user and their first farm), Farm Selector (switch between farms), Create Farm, Farm Settings (API keys and data source configuration, owner/manager only).

### Core (`/`)

The dashboard and shared infrastructure. The dashboard displays live counts for fields, livestock, equipment, buildings, open tasks, low-stock consumables, produce items, expired produce, and low feed stock. Each card links to the relevant module.

Below the summary boxes, a **commodity price strip** ("Market Prices") shows CME futures with day-over-day change (green/red) and attribution ("via Yahoo Finance · as of [date]"). 12 contracts are available (grains, livestock, dairy, fiber); users choose up to 6 to display in Farm Settings → Market Prices. Leaving all unchecked shows all synced prices. Prices sync daily at 7 AM UTC via Celery. The strip is hidden when no price data has been synced yet.

Below the price strip, an **action items feed** surfaces all overdue or urgent items across the farm in a single prioritized list: equipment maintenance past its next-service date, building maintenance past its next-due date, tasks that are overdue or marked urgent, and vet follow-up records whose next-due date has passed. Items sort oldest-first with a color-coded badge (orange = equipment, blue = building, purple = task, red = vet).

Also provides the abstract base models (`FarmOwnedModel`, `NotesMixin`, `CostMixin`) and the `base.html` template with responsive sidebar navigation.

### Land & Fields (`/land/`)

Geospatial field management. Users draw field boundaries as polygons on a Leaflet map. On save, the polygon is stored in PostGIS, the area is calculated using the NAD83 Conus Albers projection (EPSG:5070) for accuracy in the continental US, and the centroid lat/lon is extracted for weather lookups.

Saving a field triggers two Celery tasks: weather sync (Open-Meteo, 14 days of data) and soil analysis (SoilGrids, pH/organic carbon/nitrogen/texture). A GeoJSON API endpoint (`/land/fields/geojson/`) serves all field boundaries for the map view.

The field detail page has a **weather tab** that shows 14 days of data (7 history + 7 forecast) with a dashed divider between past and future dates. A **Sync Now** button triggers an immediate synchronous weather refresh. The field stores its IANA timezone (e.g. `"America/New_York"`) populated automatically from the Open-Meteo response, so forecast/history classification is always accurate in the field's local time zone rather than UTC.

**Sub-models:** `WeatherCache` (daily weather per field), `SoilSample` (manual or API-sourced soil data), `CropRecord` (crop-per-field-per-season with a status timeline: planned → seeded → growing → fertilized → harvested/failed).

**Property boundaries** (`/land/parcels/`) record the legal outline of each piece
of land a farm owns or leases, separately from its fields. A property is usually
larger than the fields on it: it also holds woodland, the farmstead, waterways and
anything else that is never planted or grazed, so total property acreage and total
field acreage answer different questions. Each property (`Parcel`) has a name, the
boundary polygon, auto-calculated acreage, an optional county tax parcel number
(APN) and a map colour. Several separate pieces of land are several properties.

The property page shows **how much of it is in fields**: each field that overlaps
it, the acres of that field *inside* the property line, and the total. It is
measured on the overlap, not each field's own acreage, so a field that crosses
the property line counts only for the part inside; and the total is taken over
the union of the overlaps, so fields drawn on top of each other are not counted
twice.

The **Farm Map** (`/land/fields/map/`) draws properties as dashed outlines
beneath the filled fields, and each layer can be toggled from the layer control.
When drawing a field, your property lines are shown dashed as a guide; when
drawing a property line, your fields are.

Field and property acreage both come from one helper (`apps/land/geo.py`,
`acreage_of`), so the two can never be measured differently. Boundaries that
cross themselves are rejected with a message asking for a redraw: they have no
meaningful area, and PostGIS cannot intersect them with a field.

### Livestock (`/livestock/`)

Animal registry with ear tag as the primary identifier (unique per farm). Tracks species (cattle, sheep, goat, pig, horse, poultry, etc.), breed, gender, reproductive status, and active/sold/deceased status. Supports photo uploads.

The detail page has tabs for veterinary records (immunizations, exams, treatments, surgeries, pregnancy checks, deworming), field movement history, feed log, and offspring lineage. Breeding lineage is tracked via self-referential sire/dam foreign keys. Moving an animal between fields automatically updates its `current_field`. The `days_in_current_field` property computes how long an animal has been in its current field based on movement history.

**Feed Management:** A sub-section at `/livestock/feed/` tracks feed inventory. `FeedType` is a global catalog of feed categories (hay, grain, silage, pellet/concentrate, supplement/mineral, fresh forage) with full CRUD views at `/livestock/feed/types/`. A seed data migration pre-populates 29 common feed types across all categories. Users can add custom feed types or remove unneeded ones. `FeedStock` tracks specific feed supplies per farm with quantity, reorder threshold, restock source (purchased, farm hay, farm grain, farm silage, pasture/forage), and storage location. Low-stock items are flagged on the dashboard. `FeedLog` records per-animal feeding events and automatically deducts from the feed stock quantity.

**Filtering:** Species, status, and free-text search on ear tag, name, and breed.

### Crops (`/crops/`)

Built around a global `CropType` catalog (with USDA NASS commodity codes),
which both plantings and harvests point at, so "Soybeans" means the same thing
on a field, in a harvest, on the catalog page and in market prices.

**Plantings and harvests are linked.** A planting (`CropRecord`, defined in the
land app because it belongs to a field) is a crop from the catalog, an optional
variety, a season, a status and a planted date. What came *off* it is recorded
as one or more harvests (`HarvestRecord`) that point back to it -- several for
crops cut or picked more than once, like hay. A planting's **yield is the total
of its harvests**, summed per unit (bales and tons are never added together),
and shown wherever plantings are listed. Each planting row has a **Record
harvest** action that opens the harvest form with the planting, field, crop and
the crop's usual unit already filled in.

A harvest's planting is optional: perennial hay or pasture often has no planting
record, and an unlinked harvest just names its field and crop. When a planting
*is* chosen, the harvest's field and crop are taken from it and must agree with
it; the form and CSV import both reject a harvest that claims a planting on a
different field or of a different crop. Harvest records also track moisture,
quality grade, cost and revenue.

**Crop Records** (`/crops/records/`) lists every planting across all fields --
crop, field, season, status, planted date, harvested yield and cost --
filterable by season, status, and crop or variety name. Plantings are created
and edited from their field's Crops tab. Each **crop type's page** shows that
crop's plantings and harvests on your farm, which is how to see how a crop did
across fields and seasons.

**Upgrading from 0.5.0 or earlier**, where a planting's crop was free text and
its yield was stored on the planting itself, is automatic: each planting's crop
name is matched to the catalog ignoring case and spacing (no guessing --
"Corn" is not assumed to mean "Corn (Grain)"), names with no match are added to
the catalog so nothing is lost (rename or merge them afterwards under Crop
Types), any yield recorded on a planting becomes a harvest of that planting, and
existing harvests are linked to a planting only when exactly one planting fits
(same field, same crop, planted on or before the harvest). Everything else stays
unlinked for you to link from the harvest form. The same rules apply to backups
and CSV files made by older versions.

**Crop Type Management:** Crop types can be created, edited, and deleted directly from the UI at `/crops/types/`. A seed data migration pre-populates 19 common US crop types (grains, oilseeds, forages, vegetables, fiber, and pulses) with their USDA commodity codes, categories, and default units. Users can add custom crop types or remove unneeded ones. A crop type that any planting or harvest uses -- on *any* farm, since the catalog is shared by every farm on an install -- cannot be deleted; the page says how many plantings and harvests use it.

A daily Celery task syncs market prices from the USDA NASS QuickStats API, storing price-per-unit by crop type, year, and state.

A separate daily task (`sync_commodity_prices`) fetches CME futures prices for 12 contracts via **yfinance** — corn, soybeans, CBOT wheat, KC HRW wheat, oats, soybean meal, soybean oil, live cattle, feeder cattle, lean hogs, Class III milk, and cotton. Tickers and unit/divisor config live in `apps/crops/constants.py`. Prices are stored in the global `CommodityPrice` model and displayed on the dashboard. Users control which contracts appear via Farm Settings → Market Prices (select up to 6; leave all unchecked to show all).

### Equipment (`/equipment/`)

Tracks farm equipment (tractors, implements, vehicles, tools) with brand, model, year, serial number, hour meter reading, purchase price, and status. The detail page shows a maintenance log with service type, description, performer, cost, and next-service scheduling (by date or hours).

### Buildings (`/buildings/`)

Building registry with PostGIS point locations for map display. Tracks building type (barn, shed, silo, greenhouse, etc.), year built, square footage, assessed value, insurance policy/cost, and property tax. A GeoJSON endpoint serves building locations for map overlays.

Maintenance records track roof, electrical, plumbing, structural, and other work with contractor, cost, and next-due-date scheduling.

### Consumables (`/consumables/`)

Inventory management for farm supplies. `ConsumableType` is a global catalog with full CRUD views at `/consumables/types/`. A seed data migration pre-populates 34 common consumable types across 7 categories (Fuel, Seed, Fertilizer, Chemical, Medical, Hardware, Bedding). Users can add custom types or remove unneeded ones. `InventoryItem` tracks specific products per farm with quantity, unit, reorder threshold, unit cost, and storage location.

`InventoryTransaction` records purchases, usage, adjustments, transfers, and waste. Saving a new transaction automatically updates the parent item's quantity. Items whose quantity drops below their reorder threshold are flagged on the dashboard.

### Employment (`/employment/`)

Employee directory with contact info, role, status, hire date, hourly rate, and emergency contact. A task kanban board organizes work into three columns: To Do, In Progress, and Done. Tasks have priority levels (low/medium/high/urgent), due dates, and assignee tracking.

Time entries log hours per employee per day, optionally linked to a specific task.

### Produce (`/produce/`)

Tracks farm produce from source to consumption. Produce items record the source (farm animal, farm crop, purchased, or donated) with optional foreign keys to the specific `Animal` or `CropRecord` that produced it. Storage type (fresh, frozen, canned, dried, preserved), expiry date, and location are tracked.

Transactions record harvesting, butchering, purchasing, consuming, selling, donating, and waste. Like consumables, saving a transaction auto-updates the item quantity. Expired items are highlighted on the list page and counted on the dashboard.

### Data I/O (`/data/`)

Unified import/export interface for all 25 data types across all modules. Each model has a django-import-export `Resource` class with human-readable foreign key resolution (e.g., animals reference fields by name, ear tags reference other animals by ear tag).

Export supports CSV and XLSX formats. Import performs a dry-run validation first, displays errors or a preview of the first 20 rows, then requires confirmation before committing. Farm-scoped models automatically have the current farm injected during import.

---

## Data Model Reference

### Abstract Bases (apps/core)

| Model | Fields | Used By |
|---|---|---|
| `FarmOwnedModel` | `farm` (FK to Farm), `created_at`, `updated_at` | All farm-scoped models |
| `NotesMixin` | `notes` (TextField) | Most models |
| `CostMixin` | `cost` (DecimalField) | VetRecord, CropRecord, MaintenanceRecord, BuildingMaintenance, HarvestRecord |

### Accounts

| Model | Key Fields |
|---|---|
| `FarmUser` | Extends AbstractUser + `phone` |
| `Farm` | `name`, `address`, `members` (M2M via FarmMembership) |
| `FarmMembership` | `user`, `farm`, `role` (owner/manager/worker/viewer) |
| `FarmSettings` | `farm` (OneToOne), `usda_nass_api_key`, `weather_enabled`, `soil_enabled`, `crop_prices_enabled`, `visible_tickers` (JSONField — list of CME ticker strings to show on dashboard; empty = show all) |

### Land

| Model | Key Fields |
|---|---|
| `Field` | `name`, `boundary` (PolygonField), `acreage` (auto-calc), `centroid_lat/lon` (auto-calc), `soil_type`, `color`, `timezone` (IANA, auto-set from Open-Meteo) |
| `Parcel` | `name`, `boundary` (PolygonField), `acreage` (auto-calc), `parcel_number` (county tax ID/APN, optional), `color` (hex, validated) -- methods: `fields_within()`, `field_coverage()` |
| `WeatherCache` | `field`, `date`, `temp_max_c`, `temp_min_c`, `precipitation_mm`, `wind_speed_max_kmh`, `weather_code` |
| `SoilSample` | `field`, `source` (manual/soilgrids/usda), `sample_date`, `depth_cm`, `ph`, `organic_carbon_pct`, `nitrogen_ppm`, `sand/silt/clay_pct`, `texture_class`, `cec` |
| `CropRecord` | `field`, `crop_type` (catalog, PROTECT), `variety`, `season`, `status` (planned->harvested), `planted_date`, `cost` -- reverse `harvests`; methods: `crop_label`, `yield_totals()` (per unit, from harvests) |

### Livestock

| Model | Key Fields |
|---|---|
| `Animal` | `ear_tag` (unique per farm), `name`, `species`, `breed`, `gender`, `repro_status`, `status`, `date_of_birth`, `date_acquired`, `purchase_price`, `weight_kg`, `current_field`, `sire`, `dam`, `photo` -- property: `days_in_current_field` |
| `VetRecord` | `animal`, `record_type` (immunization/exam/treatment/surgery/pregnancy_check/deworming), `date`, `description`, `veterinarian`, `cost`, `next_due_date`, `attachment` |
| `FieldMovement` | `animal`, `from_field`, `to_field`, `date`, `reason` -- auto-updates animal's current_field |
| `FeedType` | `name` (unique), `category` (hay/grain/silage/pellet/supplement/fresh_forage), `default_unit` -- global, not farm-scoped |
| `FeedStock` | `feed_type`, `name`, `quantity`, `unit`, `restock_source` (purchased/farm_hay/farm_grain/farm_silage/pasture_forage), `reorder_threshold`, `unit_cost`, `storage_location` -- property: `is_low_stock` |
| `FeedLog` | `animal`, `feed_stock`, `quantity`, `unit`, `date` -- auto-deducts from feed stock quantity |

### Crops

| Model | Key Fields |
|---|---|
| `CropType` | `name` (unique), `usda_code`, `category`, `default_unit` -- global, not farm-scoped |
| `MarketPrice` | `crop_type`, `year`, `state`, `price_per_unit`, `unit`, `source` -- global |
| `CommodityPrice` | `ticker` (e.g. `ZC=F`), `commodity`, `price`, `unit`, `change`, `change_pct`, `date` -- global CME futures, synced daily |
| `HarvestRecord` | `field`, `crop_type` (PROTECT), `planting` (optional `CropRecord`, SET_NULL; must agree with field and crop), `harvest_date`, `yield_amount/unit`, `moisture_pct`, `quality_grade`, `cost`, `revenue` |

`CropRecord` -- the planting -- is defined in the **land** app (it hangs off a
`Field`), and is listed at `/crops/records/`. Both it and `HarvestRecord` point
at the shared `CropType` catalog with `on_delete=PROTECT`, so a catalog entry in
use cannot be deleted out from under any farm.

### Equipment

| Model | Key Fields |
|---|---|
| `Equipment` | `name`, `brand`, `model_name`, `year`, `serial_number`, `status`, `hours`, `purchase_price`, `purchase_date`, `photo` |
| `MaintenanceRecord` | `equipment`, `maintenance_type`, `date`, `description`, `performed_by`, `hours_at_service`, `cost`, `next_service_date`, `next_service_hours` |

### Buildings

| Model | Key Fields |
|---|---|
| `Building` | `name`, `building_type`, `location` (PointField), `year_built`, `square_feet`, `assessed_value`, `insurance_policy`, `insurance_annual`, `tax_annual`, `photo` |
| `BuildingMaintenanceRecord` | `building`, `maintenance_type`, `date`, `description`, `contractor`, `cost`, `next_due_date` |

### Consumables

| Model | Key Fields |
|---|---|
| `ConsumableType` | `name` (unique), `category`, `default_unit` -- global |
| `InventoryItem` | `consumable_type`, `name`, `quantity`, `unit`, `reorder_threshold`, `unit_cost`, `storage_location` |
| `InventoryTransaction` | `item`, `transaction_type` (purchase/use/adjustment/transfer/waste), `quantity`, `date`, `unit_cost`, `reference` -- auto-updates item quantity |

### Employment

| Model | Key Fields |
|---|---|
| `Employee` | `first_name`, `last_name`, `email`, `phone`, `role`, `status`, `hire_date`, `hourly_rate`, `emergency_contact` |
| `Task` | `title`, `description`, `assigned_to`, `priority` (low/medium/high/urgent), `status` (todo/in_progress/done), `due_date`, `completed_at` |
| `TimeEntry` | `employee`, `task` (optional), `date`, `hours`, `description` |

### Produce

| Model | Key Fields |
|---|---|
| `ProduceItem` | `name`, `source` (farm_animal/farm_crop/purchased/donated), `storage_type` (fresh/frozen/canned/dried/preserved), `quantity`, `unit`, `expiry_date`, `storage_location`, `source_animal` (FK), `source_crop_record` (FK) |
| `ProduceTransaction` | `item`, `transaction_type` (harvest/butcher/purchase/consume/sell/donate/waste), `quantity`, `date`, `cost` -- auto-updates item quantity |

---

## External API Integrations

### Open-Meteo Weather API

- **URL:** `https://api.open-meteo.com/v1/forecast`
- **Auth:** None required
- **Rate limit:** 10,000 requests/day
- **Used for:** Daily weather data per field (temperature, precipitation, wind, weather code)
- **Trigger:** Automatic on field create/edit; scheduled every 6 hours for all fields
- **Data stored:** 7 days historical + 7 days forecast in `WeatherCache`

### SoilGrids REST API

- **URL:** `https://rest.isric.org/soilgrids/v2.0/properties/query`
- **Auth:** None required
- **Rate limit:** 5 requests/minute (enforced by Celery task rate limiting)
- **Used for:** Soil properties at field centroids (pH, organic carbon, nitrogen, sand/silt/clay, CEC, texture)
- **Trigger:** On field create/edit
- **Data stored:** `SoilSample` with `source="soilgrids"`

### USDA NASS QuickStats API

- **URL:** `https://quickstats.nass.usda.gov/api/api_GET/`
- **Auth:** Free API key required (set `USDA_NASS_API_KEY` in `.env`)
- **Rate limit:** 50,000 records per request
- **Used for:** Annual crop commodity prices by state
- **Trigger:** Daily at 2:00 AM via Celery Beat
- **Data stored:** `MarketPrice` records for years >= 2020

### Yahoo Finance / CME Futures (yfinance)

- **Library:** `yfinance` (Python package)
- **Auth:** None required
- **Rate limit:** Informal; once-daily sync is well within limits
- **Used for:** Daily CME futures prices for corn (`ZC=F`), soybeans (`ZS=F`), wheat (`ZW=F`), live cattle (`LE=F`), feeder cattle (`GF=F`), lean hogs (`HE=F`)
- **Trigger:** Daily at 7:00 AM UTC via Celery Beat
- **Data stored:** `CommodityPrice` — one row per ticker per date, with price, unit, and day-over-day change
- **Note:** yfinance requires `fc.yahoo.com` for its cookie auth flow. If Pi-hole is blocking this domain, whitelist `fc.yahoo.com` in Pi-hole or configure the machine to use an upstream DNS resolver directly.

---

## Getting Started (Development)

### Prerequisites

- **Python 3.12+** (3.14 works)
- **Podman** or Docker (for PostgreSQL + Redis containers)
- **System libraries:** GDAL, GEOS, PROJ (for GeoDjango)

On Fedora:

```bash
sudo dnf install gdal-libs geos proj podman podman-compose
```

On Debian/Ubuntu:

```bash
sudo apt install gdal-bin libgdal-dev libgeos-dev libproj-dev podman podman-compose
```

### Step 1: Clone and Create Virtual Environment

```bash
cd /path/to/farmsteader
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements/dev.txt   # exact pins; already includes base.txt
```

### Step 2: Start Database and Redis

```bash
podman-compose up -d
```

This starts:
- **PostGIS 16** on port 5432 (user: `farmsteader`, password: `devpassword`, database: `farmsteader`)
- **Redis 7** on port 6379

Verify they're running:

```bash
podman-compose ps
```

### Step 3: Configure Environment

Create a `.env` file in the project root (or copy `.env.example`):

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=dev-insecure-key-change-in-production-abc123xyz
DATABASE_URL=postgis://farmsteader:devpassword@localhost:5432/farmsteader
REDIS_URL=redis://localhost:6379/0
USDA_NASS_API_KEY=
```

To get a USDA API key (optional, for crop price sync), register at https://quickstats.nass.usda.gov/api/.

### Step 4: Run Migrations and Create a Superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Step 5: Build Tailwind CSS

The project uses the standalone Tailwind CSS CLI binary via `django-tailwind-cli` (no Node.js required). The binary version is pinned in `config/settings/base.py` and is downloaded automatically on first build.

This step is **required**, not optional: `static/css/dist/styles.css` is git-ignored, so a fresh checkout has no stylesheet at all. CI and the release build both run it for the same reason; installed servers get the stylesheet prebuilt in the release tarball.

Tailwind v4 is configured entirely in `assets/css/input.css` — the `@theme` block, the semantic colour tokens, and the `html.dark` overrides that implement dark mode all live there. There is no `tailwind.config.js`. The source file sits outside `static/` on
purpose, so `collectstatic` does not publish it.

```bash
make tailwind
# or: python manage.py tailwind build --force
```

The page links the stylesheet with a `?v=<mtime>` stamp, so a rebuild is picked
up by an ordinary refresh — you should not need to hard-reload after changing
the CSS.

For live rebuilds during development:

```bash
make tailwind-watch
# or: python manage.py tailwind watch
```

---

## Running the Application

You need three terminal sessions during development:

### Terminal 1: Django Dev Server

```bash
source .venv/bin/activate
make run
# or: python manage.py runserver 0.0.0.0:8000
```

Browse to **http://localhost:8000**. Log in, create a farm, and start adding data.

### Terminal 2: Celery Worker (for background tasks)

```bash
source .venv/bin/activate
make celery
# or: DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker -l info
```

The explicit settings module is not optional. `config/celery.py` defaults to
`config.settings.prod` so a production worker cannot silently boot with dev
settings, and the celery CLI -- unlike `manage.py` -- has nowhere else to pick
dev up from. See [Production Settings](#production-settings).

This processes weather sync, soil analysis, and crop price tasks. Without Celery running, these background tasks will queue but not execute.

### Terminal 3: Tailwind CSS Watch (optional)

```bash
make tailwind-watch
```

Only needed if you're modifying templates and want live CSS rebuilds. Not needed if you just ran `make tailwind` once.

### Stopping Services

```bash
# Stop the Podman containers
podman-compose down

# To also remove the database volume (WARNING: deletes all data)
podman-compose down -v
```

---

## Installing on a Server (Debian, Ubuntu, LXC or VM)

FarmSteader installs onto a fresh **Debian 13** (or recent Ubuntu) machine with
one command: a Proxmox or Incus container, a VM, or bare metal. The installer
sets up PostgreSQL + PostGIS, Redis, nginx and the app, starts everything, and
only reports success once the site actually answers with the right version.

**Size:** 2 CPU / 2 GB RAM / 10 GB disk minimum; 4 GB recommended. 1 GB is not
enough.

### Install

As root on the target machine:

```bash
curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/deploy/install.sh | bash
```

With options, download the script first:

```bash
curl -fsSLO https://raw.githubusercontent.com/mcbriderc/farmsteader/master/deploy/install.sh
bash install.sh --admin-email you@example.com --allowed-hosts farm.lan,192.168.1.40
```

| option | default |
|---|---|
| `--version X.Y.Z` | the latest release |
| `--admin-user NAME` / `--admin-email EMAIL` | `admin` / none |
| `--admin-password PASS` | generated, saved to `/root/farmsteader.creds` |
| `--allowed-hosts LIST` | `localhost`, this hostname, and its IPv4 addresses |
| `--usda-key KEY`, `--sentry-dsn DSN` | unset |
| `--no-nginx` | nginx installed; gunicorn listens on `/run/farmsteader/gunicorn.sock` |
| `--no-backups` | nightly database dump installed |
| `--dry-run` | download and verify, then print every change instead of making it |

It is non-interactive, so the same command works from a shell, Ansible or CI.
The script is only a bootstrap: it downloads the release tarball, verifies it
against the published `SHA256SUMS`, and then runs `deploy/lib/common.sh` **from
that release**, so the install steps always match the code being installed.

When it finishes it prints the address and the admin login. Open it, sign in,
and create your farm.

### What it sets up

```
/opt/farmsteader/releases/<version>/   one directory per release, root-owned (the app
                                       cannot modify its own code), each with its own
                                       .venv and collected static files
/opt/farmsteader/current  ->  releases/<version>    swapped atomically on upgrade
/etc/farmsteader/env                   configuration (0640 root:farmsteader)
/var/lib/farmsteader/media/            uploads -- outside the release, so upgrades never touch them
/var/lib/farmsteader/celerybeat-schedule
/var/backups/farmsteader/              nightly and pre-upgrade database dumps
/root/farmsteader.creds                the generated admin login (0600)
/var/log/farmsteader-install.log       full apt/pip output from install and upgrades
```

Three systemd services, each sandboxed (`ProtectSystem=strict`, `NoNewPrivileges`)
and each with its own runtime directory:

- `farmsteader-web` -- gunicorn on `/run/farmsteader/gunicorn.sock`, behind nginx
- `farmsteader-celery` -- the background worker
- `farmsteader-celerybeat` -- the scheduler

Worker counts are sized from RAM at install time (2 GB: 2 web workers and 1
celery worker) and written to `GUNICORN_WORKERS` / `CELERY_CONCURRENCY` in the
env file. Gunicorn never sizes itself from the CPU count, which inside an LXC
can be the *host's* and would start dozens of workers.

Secrets are hex, generated per install. The database password is passed to
`psql` on stdin, never on a command line.

### Upgrading

```bash
/opt/farmsteader/current/deploy/update.sh                   # to the latest release
/opt/farmsteader/current/deploy/update.sh --version 0.3.0   # to a specific one
```

The installed `update.sh` downloads and verifies the new release, then hands
over to **the new release's own** `update.sh`, so each release decides how it
is activated. Activation:

1. builds the new release's venv and static files while the old version keeps serving
2. dumps the database to `/var/backups/farmsteader/pre-upgrade-<old>-to-<new>-<time>.dump`
3. stops the services and runs migrations
4. installs the new release's systemd units and nginx config, and swaps `current`
5. starts everything and waits for `/healthz` to report the new version and `/readyz` to pass

**If migrations fail, or the new version does not come up healthy, it rolls
back automatically**: the previous release is re-linked, the pre-upgrade dump
is restored, and the old version is started and health-checked. The two most
recent releases are kept on disk.

`/etc/farmsteader/env` and everything under `/var/lib/farmsteader` are never
modified by an upgrade; a release that introduces a new setting appends it
without touching your edits. Downgrades are refused (migrations only run
forwards). Running the updater for the version already installed does nothing.

### Managing

```bash
systemctl status farmsteader-web farmsteader-celery farmsteader-celerybeat
journalctl -u farmsteader-web -f
journalctl -u farmsteader-celery -f

# after editing /etc/farmsteader/env
systemctl restart farmsteader-web farmsteader-celery farmsteader-celerybeat

# run a management command
cd /opt/farmsteader/current
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py <command>
```

`DJANGO_SETTINGS_MODULE` must be passed explicitly for `manage.py`: it defaults
to the development settings, and the env file cannot change that (it is read
after the settings module has been chosen).

**Backups:** a `pg_dump -Fc` runs nightly at 02:00 into `/var/backups/farmsteader/`
and is kept for 14 days; pre-upgrade dumps are kept for 90. Restore one with
`pg_restore`, or use the whole-farm backup/restore in the app. Uploaded files in
`/var/lib/farmsteader/media` are not in the database dump -- back that
directory up separately.

### HTTPS

The default is plain HTTP on port 80, which is right for a LAN. To serve over
HTTPS, either put a TLS proxy in front, or install certbot in the container
(`apt install certbot python3-certbot-nginx && certbot --nginx -d farm.example.com`).
Then add the hostname to `ALLOWED_HOSTS`, set `FARMSTEADER_HTTPS=1` in
`/etc/farmsteader/env`, and restart the services. That one switch turns on the
HTTPS redirect, secure cookies and HSTS.

### Proxmox VE

On a Proxmox VE 8 or 9 node, open the node's **Shell** and run:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/ct/farmsteader.sh)"
```

Choose **Default settings** for an unprivileged Debian 13 container with 2 CPU,
2 GB RAM and 10 GB disk on DHCP, or **Advanced** to set the container ID,
hostname, size, storage, static IP/gateway, VLAN, root password, admin
account, extra hostnames, USDA key, backups and version. It then:

1. picks the storage for the template and for the disk separately (on most
   clusters they differ: templates on `local`, disks on `local-lvm` or ZFS)
2. downloads the newest `debian-13-standard` template -- resolved at run time,
   never a hardcoded filename
3. creates the container (`nesting=1`, 1 GB swap, start on boot, host
   timezone, tag `farmsteader`), starts it and waits for its network
4. runs FarmSteader's own `deploy/install.sh` inside it -- the same installer
   as everywhere else -- and writes the address into the container's Notes
5. prints the address and admin login

If anything fails after the container is created, it offers to remove the
half-built container so a re-run starts clean. Cancelling any menu creates
nothing.

**Updating:** run the same command again. When FarmSteader containers (tag
`farmsteader`) exist on the node it offers to update one, which runs that
container's own `deploy/update.sh` -- including its automatic rollback.

**Unattended:** `FS_CT_DEFAULTS=1` skips every menu. Any setting can be preset
in the environment, e.g.

```bash
FS_CT_DEFAULTS=1 CT_HOSTNAME=barn var_ram=4096 NET=192.168.1.40/24 GATE=192.168.1.1 \
  FS_ADMIN_EMAIL=you@example.com bash -c "$(curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/ct/farmsteader.sh)"
```

The answers (including any admin password) reach the container as a `0600`
file, never on a command line, and are deleted when the install finishes.

**Without a cluster:** `FARMSTEADER_DRY_RUN=1 bash ct/farmsteader.sh` (from a
checkout) replaces `pct`/`pveam`/`pvesm`/`pvesh` with stubs and prints every
command it would run. `tests/test_proxmox_installer.py` pins that output: the
exact `pct create` line, template and storage selection, and that cancelling
creates nothing.

The scripts live in `ct/` (host), `install/` (inside the container) and
`misc/` (helpers), in the community-scripts layout. The GitHub copy is
updated at each release, so changes here reach the one-liner with the next
release.

### Incus quick start

```bash
incus launch images:debian/13 farmsteader -c limits.memory=2GiB -c limits.cpu=2
incus exec farmsteader -- bash -c "$(curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/deploy/install.sh)"
incus list farmsteader -c n4        # the container's address
```

The container's bridge address is reachable from the host. To reach it from
the rest of the LAN, forward a port (`incus config device add farmsteader web
proxy listen=tcp:0.0.0.0:80 connect=tcp:127.0.0.1:80`) or attach the container
to a bridged NIC so it gets an address from your router.

### Testing the installer against a local build

`--base-url` points both scripts at another release source, and `curl` reads
`file://` URLs, so a local tarball can be installed without publishing or
serving anything:

```bash
bash scripts/build-tarball.sh 0.3.0-test1      # config/__version__.py must say the same
incus exec farmsteader -- mkdir -p /root/releases/v0.3.0-test1
incus file push dist/farmsteader-0.3.0-test1.tar.gz dist/SHA256SUMS farmsteader/root/releases/v0.3.0-test1/
incus file push deploy/install.sh farmsteader/root/
incus exec farmsteader -- bash /root/install.sh --version 0.3.0-test1 --base-url file:///root/releases
```

The version in `config/__version__.py` must match the tarball's: the installer
only declares success when `/healthz` reports the version it installed.

---

## Project Structure

```
farmsteader/
├── .env                        # Environment variables (not committed)
├── .gitignore
├── pyproject.toml              # Project metadata
├── Makefile                    # Dev convenience commands
├── manage.py                   # Django CLI entry point
├── podman-compose.yml          # PostGIS + Redis for development
│
├── requirements/               # *.in = ranges (edit these); *.txt = exact pins (generated)
│   ├── base.in / base.txt      # Core dependencies
│   ├── dev.in  / dev.txt       # + debug toolbar, pytest, pytest-cov, factory-boy
│   └── prod.in / prod.txt      # + Gunicorn, Sentry
│
├── config/                     # Django project configuration
│   ├── __init__.py             # Celery app import
│   ├── celery.py               # Celery app + beat schedule
│   ├── urls.py                 # Root URL routing
│   ├── wsgi.py
│   └── settings/
│       ├── base.py             # Shared settings (DB, apps, middleware)
│       ├── dev.py              # DEBUG=True, debug toolbar
│       └── prod.py             # Security headers, HTTPS
│
├── apps/
│   ├── accounts/               # FarmUser, Farm, FarmMembership
│   │   ├── models.py
│   │   ├── views.py            # Login, register, farm select
│   │   ├── middleware.py       # CurrentFarmMiddleware
│   │   ├── context_processors.py
│   │   ├── mixins.py           # FarmAccessMixin
│   │   └── forms.py
│   ├── core/                   # Dashboard, abstract base models
│   │   ├── models.py           # FarmOwnedModel, NotesMixin, CostMixin
│   │   ├── views.py            # Dashboard with live counts
│   │   └── templates/
│   │       ├── base.html       # Responsive layout, sidebar nav
│   │       └── core/dashboard.html
│   ├── land/                   # Fields, weather, soil, crop records
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── forms.py
│   │   ├── tasks.py            # Celery: weather sync, soil sync
│   │   └── services/
│   │       ├── weather.py      # Open-Meteo API client
│   │       └── soil.py         # SoilGrids API client
│   ├── livestock/              # Animals, vet records, movements, feed
│   ├── crops/                  # Crop types, market prices, harvests
│   │   └── tasks.py            # Celery: USDA NASS price sync
│   ├── equipment/              # Equipment, maintenance records
│   ├── buildings/              # Buildings (PostGIS points), maintenance
│   ├── consumables/            # Inventory items, transactions
│   ├── employment/             # Employees, tasks, time entries
│   ├── produce/                # Produce items, transactions
│   └── data_io/                # Import/export, backup/restore
│       ├── resources.py        # 24 farm-scoped ModelResource classes
│       ├── backup.py           # Whole-farm archive: export_farm / restore_farm
│       ├── views.py            # Export/import + backup/restore endpoints
│       ├── management/commands/ # farm_backup.py, farm_restore.py
│       └── urls.py
│
├── tests/                      # pytest test suite (not deployed to LXC)
│   ├── conftest.py             # Fixtures: user, farm, farm_client
│   ├── factories.py            # factory_boy model factories
│   ├── test_middleware.py      # CurrentFarmMiddleware behavior
│   ├── test_models.py          # Model properties and computed fields
│   ├── test_services.py        # Soil and data_io helper functions
│   ├── test_backup.py          # Farm backup/restore round-trip and validation
│   ├── test_views_core.py      # Dashboard views
│   ├── test_views_land.py      # Field CRUD views
│   ├── test_views_livestock.py # Animal CRUD views
│   ├── test_views_equipment.py # Equipment CRUD views
│   ├── test_views_buildings.py # Building CRUD views
│   ├── test_views_consumables.py
│   └── test_views_employment.py
│
├── sonar-project.properties    # SonarQube scanner config (coverage, exclusions)
│
├── static/
│   ├── css/
│   │   ├── input.css           # Tailwind entry point
│   │   └── dist/styles.css     # Built CSS (git-ignored)
│   └── vendor/js/
│       ├── htmx.min.js
│       ├── alpine.min.js
│       ├── leaflet.js
│       ├── leaflet.draw.js
│       └── turf.min.js
│
├── ct/farmsteader.sh           # Proxmox VE host installer (creates the container)
├── install/                    # Runs inside that container; calls deploy/install.sh
├── misc/                       # build.func (host) / install.func (container) helpers
├── deploy/                     # Server install (ships in the release tarball)
│   ├── install.sh              # Bootstrap: fetch + verify a release, then run its common.sh
│   ├── update.sh               # In-place upgrade with automatic rollback
│   ├── lib/common.sh           # All install/upgrade steps (fs_* functions)
│   ├── gunicorn.conf.py        # Env-driven gunicorn config
│   ├── nginx/farmsteader.conf  # Reverse proxy + static/media
│   └── systemd/                # farmsteader-{web,celery,celerybeat}.service
│
├── media/                      # User uploads (git-ignored)
└── staticfiles/                # Collected static (git-ignored)
```

---

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Yes | `config.settings.dev` | Settings module to use |
| `SECRET_KEY` | Yes | -- | Django secret key |
| `DATABASE_URL` | Yes | -- | PostGIS database URL (`postgis://user:pass@host:port/dbname`) |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for Celery broker |
| `USDA_NASS_API_KEY` | No | `""` | USDA NASS API key for crop price sync |
| `FARMSTEADER_MAX_RESTORE_BYTES` | No | `2147483648` | Largest uncompressed size accepted from an uploaded farm backup |
| `ALLOWED_HOSTS` | Prod only | -- | Comma-separated list of allowed hostnames |
| `CSRF_TRUSTED_ORIGINS` | No | `[]` | Scheme-qualified origins (`https://farm.example.com`), unlike `ALLOWED_HOSTS` |
| `FARMSTEADER_HTTPS` | No | `0` | Master TLS switch (see [Production Settings](#production-settings)) |
| `SECURE_SSL_REDIRECT` | No | `FARMSTEADER_HTTPS` | Individual override |
| `SESSION_COOKIE_SECURE` | No | `FARMSTEADER_HTTPS` | Individual override |
| `CSRF_COOKIE_SECURE` | No | `FARMSTEADER_HTTPS` | Individual override |
| `SECURE_HSTS_SECONDS` | No | `31536000` if HTTPS else `0` | Individual override |
| `USE_PROXY_SSL_HEADER` | No | `1` | Trust `X-Forwarded-Proto` from the reverse proxy |
| `STATIC_ROOT` | No | `<repo>/staticfiles` | Where `collectstatic` writes |
| `MEDIA_ROOT` | No | `<repo>/media` | Upload destination |
| `CONN_MAX_AGE` | No | `60` prod, `0` elsewhere | Persistent DB connection lifetime, seconds |
| `CONN_HEALTH_CHECKS` | No | `True` prod, `False` elsewhere | Validate a reused connection before handing it out |
| `LOG_LEVEL` | Prod only | `INFO` | Root log level |
| `SENTRY_DSN` | No | `""` | Empty means `sentry_sdk` is never imported |
| `SENTRY_ENVIRONMENT` | No | `production` | Sentry environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Sentry performance sampling |

### Makefile Commands

| Command | Description |
|---|---|
| `make run` | Start Django development server on 0.0.0.0:8000 |
| `make celery` | Start Celery worker |
| `make tailwind` | Build Tailwind CSS (downloads CLI binary automatically on first run) |
| `make tailwind-watch` | Watch and rebuild Tailwind CSS on changes |
| `make migrate` | Run Django migrations |

### Production Settings

`config/settings/prod.py` is built around one switch. A default LAN install
terminates plain HTTP on nginx port 80, so **TLS is off unless you ask for it**:

```bash
FARMSTEADER_HTTPS=1        # SSL redirect + HSTS + secure session/CSRF cookies
```

Leaving it off is what makes a LAN install reachable at all. Turning it on
without HTTPS actually terminating in front means `SECURE_SSL_REDIRECT` sends
the browser to `https://`, nginx is not listening there, and every request
redirect-loops. Each setting also has an individual override for unusual
topologies (TLS terminated further upstream, say).

`SECURE_PROXY_SSL_HEADER` is trusted by default, which is safe here because
nginx **sets** rather than appends `X-Forwarded-Proto $scheme` on every proxied
request, overwriting whatever a client sent. Set `USE_PROXY_SSL_HEADER=0` if the
app is ever exposed with no proxy in front.

To verify a configuration before deploying it:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
ALLOWED_HOSTS=farm.example.com FARMSTEADER_HTTPS=1 \
    python manage.py check --deploy --fail-level WARNING
```

CI runs exactly this (see `scripts/ci/test.sh`). Note the two details that make
it meaningful: every finding Django reports here is a `WARNING`, so at the
default `ERROR` level the check passes unconditionally; and it must run with
`FARMSTEADER_HTTPS=1`, because the secure configuration is the one worth gating
on.

#### Which settings module gets used

`config/celery.py` sets `DJANGO_SETTINGS_MODULE` to **`config.settings.prod`**
when nothing else has, and `config/__init__.py` imports it eagerly -- so it runs
before the equivalent line in `wsgi.py`/`asgi.py` and is what actually decides.
Defaulting to prod means a process started without the variable fails to boot
rather than silently coming up with `DEBUG=True` and `ALLOWED_HOSTS=["*"]`.

`.env` cannot influence this: django-environ reads that file from inside
`base.py`, by which point the settings module has already been resolved. Dev
entrypoints therefore say so themselves -- `manage.py` defaults to
`config.settings.dev`, and `make celery` exports it. In production systemd's
`EnvironmentFile=` sets the real process environment, which works.

### Health Endpoints

Two unauthenticated JSON endpoints, deliberately registered **without** a
trailing slash so `APPEND_SLASH` cannot 301 a probe into looking healthy:

| Endpoint | Purpose | Codes |
|---|---|---|
| `/healthz` | Liveness. Touches nothing external. | `200` |
| `/readyz` | Readiness. `SELECT 1` plus a Redis ping. | `200` / `503` |

```console
$ curl -s localhost/healthz
{"status": "ok", "version": "0.2.0"}

$ curl -s localhost/readyz
{"status": "degraded", "version": "0.2.0",
 "checks": {"database": "ok", "redis": "error"}}
```

`/healthz` stays deliberately dependency-free: a liveness probe that fails when
Postgres blips gets the *web* process restarted, which does not fix Postgres and
does drop every in-flight request. Use `/readyz` for dependency state -- it
reports per-check status so an operator can tell which service to go and look at.

Both paths are listed in `CurrentFarmMiddleware.EXEMPT_PATHS`. Without that an
unauthenticated probe is redirected to the login page, and any checker that
follows redirects or accepts a `3xx` reports the app healthy while it is
completely broken. `tests/test_health.py` guards this.

### Django Admin

The Django admin is available at `/admin/` and can be used for direct database access and debugging. Log in with your superuser credentials.

---

## Import / Export

The Data I/O module at `/data/` provides CSV and XLSX import/export for 25 data types organized by module. These are per-table spreadsheets for bulk editing. Crops are referenced by catalog name (matched ignoring case; an unknown crop is a row error -- add it under Crop Types first), and a harvest's planting by `Field | Crop | Season`, plus `| Variety` when the planting has one. Every rejected row is listed with its reason before anything is imported. Planting files exported by 0.5.0 and earlier, with a `crop_name` column and yields on the planting, still import. To copy a whole farm — for a reinstall or an upgrade — use [Backup & Restore](#backup--restore) instead, which also carries field boundaries, photos, and farm settings.

| Module | Exportable Data Types |
|---|---|
| Land | Fields, Soil Samples, Crop Records |
| Livestock | Animals, Vet Records, Field Movements, Feed Types, Feed Stocks, Feed Logs |
| Crops | Crop Types, Market Prices, Harvest Records |
| Equipment | Equipment, Maintenance Records |
| Buildings | Buildings, Building Maintenance |
| Consumables | Consumable Types, Inventory Items, Inventory Transactions |
| Employment | Employees, Tasks, Time Entries |
| Feed | Feed Types, Feed Stocks, Feed Logs |
| Produce | Produce Items, Produce Transactions |

### Exporting

Click **CSV** or **XLSX** next to any data type on the `/data/` page. The export includes all records for the current farm (or all records for global types like Crop Types). Foreign keys are exported as human-readable values (e.g., animal ear tags, field names) rather than database IDs. Field boundaries and building locations export as WKT geometry (`POLYGON ((...))`), which imports back unchanged.

### Importing

1. Click **Upload** next to the data type.
2. Select a CSV or XLSX file. The column headers should match the export format -- export existing data first to see the expected format.
3. Click **Preview Import**. The system validates all rows without writing to the database (dry run).
4. If errors are found, they're displayed with row numbers. Fix the file and re-upload.
5. If validation passes, a preview of the first 20 rows is shown. Re-upload the same file and click **Confirm Import** to commit.

For farm-scoped data, the current farm is automatically assigned to imported records. Every lookup an import performs -- both the row-matching key and any foreign key resolved by name -- is confined to the current farm, so a file exported by one farm can never read or modify another farm's records. Importing a file that still carries another farm's `id` column creates new records rather than reusing those ids.

---

## Backup & Restore

Available at `/data/backup/`. Produces a single self-contained `.zip` holding **everything in one farm**, and restores it on any FarmSteader install. This is the tool for "export before reinstalling, then re-import to be safe".

Unlike the per-table CSV export, a backup carries PostGIS field boundaries and building locations, uploaded photos and vet attachments, farm settings, exact created/updated timestamps, and the complete foreign-key graph.

### Archive format

```
farmsteader-backup-<farm>-<YYYYMMDD-HHMMSS>.zip
├── manifest.json     format version, app version, per-model counts, field lists, SHA-256 of data.json
├── data.json         one entry per model; geometry as GeoJSON, decimals as strings
└── media/            photos and attachments, at their stored paths
```

Geometry travels as GeoJSON text rather than binary WKB, so an archive moves between PostGIS versions unchanged. Global catalog references (Crop Types, Feed Types, Consumable Types) are stored by name, and the archive carries a copy of each referenced catalog row -- so a restore still succeeds if a later release renamed or dropped a seed entry.

### Restoring

Restoring **always creates a new farm** and makes you its owner; your current farm is never modified. Upload the archive at `/data/backup/`, confirm, and you are switched to the restored farm. Delete the old one manually once you have checked it over.

The whole archive is validated before anything is written -- checksum, member paths (traversal and oversize archives are rejected), and a field-by-field comparison against this version's models. If the archive comes from a **newer** FarmSteader and holds fields this version lacks, the restore refuses until you tick *Discard unknown fields*. If it comes from an **older** one, missing optional fields take their defaults and a warning is recorded. Archives carry a format version; when the archived data changed shape between releases, older archives are upgraded on restore -- for example, a backup made by 0.5.0 or earlier has its plantings linked to the crop catalog and their yields turned into harvests, by the same rules as the database upgrade (see Crops). A backup made by a newer release than the one restoring it is refused with a message to upgrade first. Everything else runs in a single transaction, so a failed restore leaves no partial farm behind.

### What is not included

| Left out | Why |
|---|---|
| Weather history (`WeatherCache`) | Re-fetched from Open-Meteo within hours; can be tens of thousands of rows |
| Market and commodity prices | Global data, re-synced by Celery |
| Users, passwords, memberships | Credentials. The user performing the restore becomes the new farm's owner |

> **The archive is not encrypted and contains your USDA NASS API key.** Store it somewhere private.

### Command line

Useful for a scripted backup before an upgrade, or a headless restore on a fresh install:

```bash
python manage.py farm_backup --farm 1 --output backup.zip
python manage.py farm_backup --farm "Example Farm" --output backup.zip

python manage.py farm_restore backup.zip --owner alice
python manage.py farm_restore backup.zip --owner alice --farm-name "Recovered Farm"
python manage.py farm_restore backup.zip --owner alice --allow-dropped-fields
```

`FARMSTEADER_MAX_RESTORE_BYTES` (default 2 GiB) caps the uncompressed size a restore will accept.

Two notes on restored farms. Media files are written outside the database transaction, so a failed restore can leave unreferenced files in `MEDIA_ROOT`; they are harmless. And in production, Celery begins populating weather for the restored fields on its next run -- in development nothing happens until you start a worker with `make celery`.

---

## Celery Tasks & Scheduling

### Periodic Tasks (Celery Beat)

| Task | Schedule | Description |
|---|---|---|
| `apps.land.tasks.sync_all_weather` | Every 6 hours | Queues weather sync for every field |
| `apps.crops.tasks.sync_crop_prices` | Daily at 2:00 AM UTC | Fetches USDA NASS crop prices |
| `apps.crops.tasks.sync_commodity_prices` | Daily at 7:00 AM UTC | Fetches CME futures prices via yfinance |

### On-Demand Tasks

| Task | Trigger | Description |
|---|---|---|
| `sync_weather_for_field(field_id)` | Field create/edit; "Sync Now" button | Fetches 14 days of weather data from Open-Meteo; also updates field timezone |
| `sync_soil_data_for_field(field_id)` | Field create/edit | Fetches soil properties from SoilGrids (rate limited: 5/min) |

### Monitoring Celery

```bash
# Watch task execution in real time
celery -A config worker -l info

# Check scheduled tasks
celery -A config inspect scheduled

# Check active tasks
celery -A config inspect active
```

In production (LXC), use journalctl:

```bash
journalctl -u farmsteader-celery -f
journalctl -u farmsteader-celerybeat -f
```

## Releases

The version lives in exactly one place, `config/__version__.py`, and is exposed
as `settings.APP_VERSION` and reported by `/healthz`. `pyproject.toml`
deliberately carries no `version` key -- there is no `[build-system]` table, so
nothing reads it and a second copy would only drift.

### Cutting a release

```bash
scripts/release.sh 0.3.0
```

That bumps the version module, promotes the `## [Unreleased]` section of
`CHANGELOG.md` to `## [0.3.0] - <today>`, commits, and creates an annotated tag.
**It never pushes.** Pushing is what triggers publication, so it stays a
separate deliberate command; the script prints both it and the undo.

It refuses to run on a dirty tree, against an existing tag, on a malformed
version, when `[Unreleased]` is empty, or **when HEAD is not on `master`**. All
validation happens before any file is touched, and a rollback trap restores the
tree if a later step fails.

**Releases are always cut from `master`.** A tag on a feature branch would build
a tarball from a commit that is not on the mainline, and would publish unmerged
work as a release on the public mirror. Both `release.sh` and the release workflow
enforce it -- the script when it creates the tag, the workflow (via
`git merge-base --is-ancestor`) because a tag can also be pushed by hand. Set
`FS_RELEASE_BRANCH` to override locally, or the `RELEASE_BRANCH` repo variable
in CI.

### Building the artifacts

```bash
scripts/build-tarball.sh            # version from config/__version__.py
scripts/build-tarball.sh 0.2.0-test # or an explicit one
```

Produces `dist/farmsteader-<version>.tar.gz` and a `dist/SHA256SUMS` entry.

The archive comes from `git archive`, not `tar` over the working tree. That is
the point: content is drawn from a tree object, so no untracked file, no
`.venv`, no stray `.env` and no editor backup can reach a published artifact
even if one is sitting in the directory. Exclusions are `export-ignore`
attributes in `.gitattributes`. Two files are appended afterwards because
neither is tracked: the compiled stylesheet (`static/css/dist/` is git-ignored)
and a generated `VERSION`.

Builds are reproducible -- ownership is pinned, mtimes come from the commit date
rather than the clock, and `gzip -n` omits its timestamp header -- so the same
commit always yields a byte-identical tarball whose checksum can be re-verified
independently.

The script asserts its own output and fails the build otherwise: `VERSION`, the
stylesheet and `manage.py` present; exactly one root directory (installers `cd`
into it by name); and nothing from `.git`, `.venv`, `tests`, `scripts` or
`.forgejo`. Those live in the script rather than in CI so a local build is held
to the same standard.

Verifying a download uses the same idiom the installers will:

```bash
grep " farmsteader-0.2.0.tar.gz$" SHA256SUMS | sha256sum -c -
```

> The checksum protects against corruption, not compromise: CI publishes both
> the tarball and its checksum. Before advertising a public one-liner installer,
> add `minisign` signing with the public key embedded in the installer.

### Publishing (`.forgejo/workflows/release.yml`)

Pushing a `v*` tag runs the release workflow. It has two jobs:

- **`test`** — the same gate as CI. A tag that cannot pass the suite must not
  become a release.
- **`release`** — runs in `debian:13-slim`, **not** a Python image. Because
  `build-css.sh` drives the standalone binary, this job needs no interpreter,
  no Django and no GDAL; it is entirely git, tar and curl.

Order of operations: check out the tag → assert the tag, `config/__version__.py`
and `CHANGELOG.md` all agree → build the tarball → extract the release notes →
create the Forgejo release and upload the tarball and `SHA256SUMS` → download
what was just published and verify its checksum.

That last step is the point of the exercise. Everything before it verifies a
file we built locally; only the smoke test proves the bytes on the server are
the bytes we made. Silent truncation on upload is otherwise something you first
hear about from a user with a broken install.

**Rehearsing.** Run the workflow manually from the Actions tab: the
`workflow_dispatch` path defaults to `dry_run`, so it builds and verifies
everything and publishes nothing. An accidental "Run workflow" click cannot
publish.

**Re-running is safe.** Publishing reuses an existing release for the tag rather
than creating a duplicate, and deletes an asset of the same name before
uploading — the API otherwise accepts both and leaves two files with one name,
with no way to say which a download returns.

A version with a prerelease suffix (`v0.3.0-rc1`) is marked as a prerelease on
the forge, so it does not become "latest" for update checks. Prereleases are
cheap to delete, which makes them the right way to exercise this end to end.
The tag must still equal `v` + `config/__version__.py` exactly, so an rc needs
the version file to say `0.3.0-rc1` too; tagging `v0.2.0-rc1` on a tree at
`0.2.0` is rejected before anything is built.

**Required configuration** (Forgejo repo or user settings → Actions):

| Name | Kind | Purpose |
|---|---|---|
| `RELEASE_TOKEN` | secret | Release API (`write:repository`) |
| `GH_REPO` | variable | Public mirror as `owner/repo` -- `mcbriderc/farmsteader`. No URL, no `.git` |
| `GH_TOKEN` | secret | GitHub push + release (classic PAT: `repo`) |

The obvious name, `FORGEJO_TOKEN`, is not allowed: Forgejo rejects any secret
starting with `FORGEJO_`, `GITEA_` or `GITHUB_`.

`RELEASE_TOKEN` is a PAT rather than the automatic `github.token`: the auto-token
works for `git fetch` (CI relies on it) but its release-API scope varies by
Forgejo version, and there is no portable `permissions:` block to widen it.

The GitHub mirror steps stay dormant until `GH_REPO` is set, so the workflow is
usable against Forgejo alone.

**The mirror publishes snapshots, not history.** Forgejo is where development
happens; GitHub is a distribution channel. On each release,
`scripts/publish-snapshot.sh` builds one commit holding that release's files
minus the paths listed in `.forgejo/mirror-exclude` (personal notes, internal
docs, CI config), parents it on the previous release's snapshot, and pushes it
as `master` plus the tag. Commit history, commit messages and excluded files
never leave Forgejo, which is the only arrangement that can be audited in
advance -- a filtered history would have to anticipate every past version of
every file.

- **To keep something off GitHub**, add its path to `.forgejo/mirror-exclude`
  before the release that would carry it. The list is itself under the
  excluded `.forgejo/`, so it is never public.
- **Deterministic:** a neutral author (`FarmSteader Releases`) and the tagged
  commit's date mean the same release always produces the same commit ID, so a
  re-run is a no-op.
- **A published tag never moves.** If the tag already exists on GitHub with the
  same tree the step does nothing; with a different tree it fails.
- **Fast-forward only**, never a force-push. Edits made directly on GitHub are
  kept in its history but not carried into the next release's files, so make
  every change on Forgejo.
- A re-run of a release uses the script *as of that tag*, so tags older than
  the script cannot be mirrored by re-running them.

### Building the stylesheet

```bash
scripts/build-css.sh [output-path]
```

Drives the pinned standalone Tailwind binary directly. Deliberately not
`manage.py tailwind build`, which boots Django and therefore needs
`SECRET_KEY`, a parseable `DATABASE_URL` and a working GDAL -- none of which
have anything to do with compiling CSS. Avoiding that is what lets the release
job run without Python at all.

The binary is downloaded to a temporary name, checked against a pinned upstream
SHA-256, and only then moved into `.django_tailwind_cli/` (the same cache
`manage.py tailwind` uses) and executed. An interrupted download therefore
cannot leave a truncated binary that later runs trust. The pin is also
cross-checked against `TAILWIND_CLI_VERSION` in `base.py`, so `make tailwind`
and a released artifact cannot be compiled by different versions unnoticed.

Bumping Tailwind means changing `TAILWIND_VERSION` in the script,
`TAILWIND_CLI_VERSION` in `base.py`, and every checksum in the `case` block
together -- they come from upstream's own `sha256sums.txt` release asset.

## Python Dependencies (locked)

Requirements are split into two layers, in the pip-tools style:

| file | what it is | who edits it |
|---|---|---|
| `requirements/{base,dev,prod}.in` | direct dependencies as **ranges**, each with a ceiling | you |
| `requirements/{base,dev,prod}.txt` | the full resolved tree as **exact pins**, transitives included | `scripts/lock-deps.sh` only |

Everything installs from the `.txt` files -- CI, the release job, deploys and
local dev -- so all of them run the same versions. Each compiled file is
complete on its own: `dev.txt` and `prod.txt` already contain everything in
`base.txt`, and they are constrained against it (`-c base.txt`), so a shared
package can never resolve to one version in dev and another in prod.

Before this, every requirement was an unbounded `>=`. CI resolved whatever was
newest at run time, which is how a commit touching no Python once failed the
`check --deploy` gate, and why CI was testing Django 6.1 while local venvs still
ran 5.2.

The ceilings sit at the next major (next minor for `0.x` packages, where a
minor may break). The lock gives reproducibility; the ceiling stops an
`--upgrade` from crossing a breaking release without someone deciding to.

```bash
scripts/lock-deps.sh                            # re-sync after editing a .in file
scripts/lock-deps.sh --upgrade                  # move everything, within ceilings
scripts/lock-deps.sh --upgrade-package celery   # move one package
.venv/bin/pip install -r requirements/dev.txt   # bring your venv in line
```

The script resolves inside `python:3.13` via podman (or docker), not in the
local venv: 3.13 is what CI and the Debian 13 deploy target run, and a resolver
answers for the interpreter it runs under. Without flags it keeps existing pins
and moves only what a `.in` edit forces. Running it twice produces identical
files. The lock also installs cleanly on the 3.14 dev interpreter.

To add a dependency: add it to the right `.in` file **with a ceiling**, run the
script, and commit the `.in` and `.txt` changes together.

## Continuous Integration (Forgejo Actions)

CI runs on the self-hosted Forgejo instance via Forgejo Actions (GitHub Actions
compatible). The workflow lives at `.forgejo/workflows/ci.yml` and triggers on
pushes to `master` and on pull requests.

### What the pipeline does

The `test` job runs inside the official `python:3.13` container (matching the
Debian 13 deployment target, so an interpreter difference cannot be the thing
that works in CI and breaks in production; local dev runs 3.14)
with `postgis/postgis:16-3.4` (database) and `redis:7-alpine` (Celery
broker/result backend) service containers. Redis is required because some views
enqueue Celery tasks on request; without a reachable broker those requests error.
Service containers are addressed by their service name (`postgres`, `redis`) on
the job's Docker network -- not `localhost`:

1. **Checkout** via a plain `git` fetch (not `actions/checkout`, which is a JavaScript action needing `node` that the `python:3.13` container lacks). A full fetch gives SonarQube blame history.
2. **Install GeoDjango system libraries** -- `gdal-bin`, `libgdal-dev`, `libgeos-dev`, `libproj-dev`, `binutils` (required by `django.contrib.gis`).
3. **Install Python dependencies** from `requirements/dev.txt`.
4. **Run `scripts/ci/test.sh`**, which builds the Tailwind stylesheet, runs `pytest` (producing `coverage.xml`, config in `pyproject.toml`), then runs `manage.py check --deploy --fail-level WARNING` against `config.settings.prod`.
5. **SonarQube scan** -- downloads SonarScanner CLI and runs it against `sonar-project.properties`. Skipped automatically when the `SONAR_TOKEN` secret is not set.

Steps 4's contents live in a shell script rather than inline YAML so the release
workflow can run the identical gate. Reusable workflows are not an option: they
are resolved by a JavaScript action, and there is no `node` in the job container.
The Tailwind build must come first because `static/css/dist/` is git-ignored and
`tests/test_theming.py` fails (rather than skips) when `CI` is set.

The database is reached at host `postgres` (the service name) on the job's Docker
network, so CI's `DATABASE_URL` is
`postgis://farmsteader:devpassword@postgres:5432/farmsteader`. No `.env` file is
present in CI; `SECRET_KEY`, `DATABASE_URL`, etc. come from the workflow's `env:`
block and repo secrets.

### Runner notes (Podman)

The runner is a Debian LXC on Proxmox using **Podman** with Docker emulation, which
requires two accommodations already baked into the workflow:

- **Fully-qualified image names** (`docker.io/library/python:3.14`, `docker.io/postgis/postgis:16-3.4`) because Podman's `registries.conf` does not resolve unqualified Docker Hub names non-interactively.
- **An explicit "Wait for PostGIS" step** using `pg_isready`, because Podman's Docker-compatible API does not reliably report service-container health to the runner.
- **A manual `git` checkout** instead of `actions/checkout`. JavaScript actions run via `node` *inside* the job container; since the job uses `python:3.14` (no Node), any `uses:` step would fail with `crun: executable file 'node' not found`. Keeping every step a `run:` step avoids Node entirely.

The runner process must point at the Podman socket. Enable it
(`systemctl enable --now podman.socket`) and set the socket in the runner's
`config.yml` (`container.docker_host: unix:///run/podman/podman.sock`, or the
rootless path `unix:///run/user/<uid>/podman/podman.sock`) or via `DOCKER_HOST`.
Docker-in-LXC also needs `features: nesting=1,keyctl=1` on the container.

### Required configuration

- **Runner:** a Forgejo Actions runner with the `linux-amd64` label and working container support (see Podman notes above). If you re-register the runner with different labels, update `runs-on` in the workflow to match.
- **Secrets** (repo *Settings -> Actions -> Secrets*), only needed for the SonarQube step:
  - `SONAR_HOST_URL` -- e.g. `http://sonarqube.local:9000`
  - `SONAR_TOKEN` -- a SonarQube project analysis token

Bump `SONAR_SCANNER_VERSION` in the workflow to update the scanner CLI.
