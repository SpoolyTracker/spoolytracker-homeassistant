# SpoolyTracker – Home Assistant Integration — Design

Date: 2026-07-05
Status: Approved for V1 build

## 1. Purpose

A HACS-friendly custom integration (`spoolytracker`) that connects Home Assistant
to a SpoolyTracker instance via an API token and lets automations log filament
consumption when a 3D print finishes. The integration is **printer-agnostic**: it
exposes generic services and never depends on the Bambu Lab integration.

## 2. Grounding in the REAL SpoolyTracker API

The integration targets the existing token-based open API. Verified from source
(`apps/api/src/public-api/*`):

- Base path: `/public-api/v1`
- Auth: `Authorization: Bearer <key>` (also accepts `x-api-key: <key>`)
- Responses are wrapped in `{ "data": ... }`.

| Method & path | Scope | Body / notes |
|---|---|---|
| `GET /filaments` | `filaments:read` | `{data:[filament]}` — a "spool" is a *filament* |
| `GET /filaments/{id}` | `filaments:read` | `{data:filament}` |
| `PATCH /filaments/{id}/stock` | `stock:write` | `{weightRemaining}` |
| `GET /consumption` | `consumption:read` | history |
| `POST /consumption` | `consumption:write` | log a consumption (main call) |
| `GET /analytics/stock` | `stock:read` | `{spoolCount, lockedCount, lowStockCount, totalInitial, totalRemaining, totalConsumed}` |
| `GET /analytics/consumption` | `analytics:read` | aggregates |

Filament object fields we rely on: `id` (int), `spoolReference`, `brand.name`,
`material.name`, `types[].name`, `color`, `colorHex`, `colorName`, `colors[]`,
`weightInitial`, `weightRemaining`, `virtualWeightRemaining`, `lowStockThreshold`,
`lowStockThresholdType`, `diameterMm`, `densityGcm3`, `isLocked`.

`POST /consumption` accepted body:
`{ filamentId(int, required), amount(grams), type: 'MANUAL'|'PRINT'|'FAIL',
notes, date, externalJobId, isPlanned, printTaskId, printStatus,
plannedPrintAmount, failureProgressPercent }`.

### Reconciliation with the brief (important)

The brief assumed a richer API. Real differences and how we handle them:

1. **`spool_id` is an integer `filamentId`.** The service keeps the friendly name
   `spool_id` but coerces to int before sending.
2. **No `length_used_m`, `source`, `printer_name`, `ams_*`, `material`, `color`,
   or free-form `metadata` fields exist server-side.** Decision (chosen):
   **map into `notes` + `externalJobId`.** We send `type='PRINT'`, `amount=grams`,
   `externalJobId=<job_name or job id>`, and fold the rest into a compact,
   human-readable `notes` string, e.g.
   `HA · Bambu P1S · AMS1/slot3 · PETG black (Bambu) · 13.2m · src=home_assistant`.
   The full structured payload is *also* emitted as an HA event
   (`spoolytracker_consumption_logged`) so nothing is lost and dashboards/automations
   can consume it. `length_used_m`, `source`, `metadata` become API TODOs.
3. **No public `projects` endpoint** (the `projects:read` scope has no controller).
   `get_projects()` and the `project_id` service field are kept but marked TODO;
   `project_id`, if supplied, is added to `notes` only. No project entities in V1.
4. **No dedicated token-validation endpoint.** `validate_token()` calls
   `GET /analytics/stock` (cheap, needs only `stock:read`) and treats 401/403 as
   invalid token → triggers reauth.

## 3. Architecture / modules

```
custom_components/spoolytracker/
  __init__.py        setup/unload, service registration, coordinator wiring
  manifest.json      domain, version, iot_class=cloud_polling, config_flow
  const.py           DOMAIN, endpoint constants (single source of URLs), defaults, keys
  api.py             SpoolyTrackerApiClient (aiohttp via HA session) — only place with URLs
  coordinator.py     SpoolyTrackerCoordinator (DataUpdateCoordinator) — spools + stats
  matching.py        SpoolResolver — the 5 strategies, pure/testable
  config_flow.py     UI config flow + options flow + reauth
  services.py        service handlers (registered from __init__)
  services.yaml      service schema/UI metadata
  sensor.py          5 sensors
  select.py          active-spool selects (global + per configured slot)
  diagnostics.py     redacted diagnostics
  translations/en.json, translations/fr.json
  brand/             icon.png, icon@2x.png, logo.png, logo@2x.png (+ dark_*)
```

Design principles: URLs live only in `const.py`; `api.py` is a thin typed client
returning parsed dicts and raising typed exceptions
(`SpoolyTrackerAuthError`, `SpoolyTrackerConnectionError`, `SpoolyTrackerApiError`);
`matching.py` is pure logic over the coordinator's spool list so it is unit-testable
without HA; services orchestrate resolve → POST → refresh.

## 4. Data flow — `log_consumption`

1. Automation calls `spoolytracker.log_consumption` with grams + context.
2. `SpoolResolver.resolve(call_data, slot_map, coordinator.data)` runs enabled
   strategies **in priority order**:
   - **S1 direct** `spool_id` → use it.
   - **S2 slot map** (`printer_name`,`ams_unit`,`ams_slot`|`external`) → configured `spool_id`.
   - **S4 active select** for that printer/slot → selected `spool_id`.
   - **S3 metadata** (material/color/brand/filament_profile/spoolReference) → filter spools.
3. Outcomes:
   - Exactly one match → POST consumption; on success fire event + refresh coordinator.
   - Zero match → **S5 fallback**: no silent write. Fire `spoolytracker_consumption_unresolved`
     event, log a warning, update `sensor...last_consumption`/a pending attribute, raise
     `HomeAssistantError` with a clear message.
   - Multiple matches → refuse unless `allow_ambiguous_match: true` (then pick a
     deterministic best/first and note ambiguity); otherwise raise `HomeAssistantError`.

Strategy order S1>S2>S4>S3 (most reliable first); S3 is fallback-only and never
auto-logs on ambiguity. Each strategy can be toggled in options.

## 5. Slot mapping storage

`set_slot_spool` / `clear_slot_spool` maintain a dict in
`config_entry.options["slot_map"]`, keyed by a normalized string
`"<printer>|ams<unit>/slot<slot>"` or `"<printer>|external"`. Persisted via
`hass.config_entries.async_update_entry`. Selects and S2/S4 read from it.

## 6. Entities (kept minimal for V1)

Sensors: `total_spools`, `low_stock_spools`, `total_remaining_weight` (g),
`last_consumption` (state = grams of last log, attrs = full context),
`api_status` (ok/unauthorized/unavailable). Device = the SpoolyTracker instance.

Selects: one global `active_spool`; plus one `active_spool` select per configured
slot (created from `slot_map`). Options = spool labels
(`#id · brand material colorName`); we do **not** create a select per spool. To
avoid huge option lists, the resolver accepts either the friendly label or a raw id.

## 7. Config & options flow

Config: `base_url` (required, normalized/trim trailing slash), `api_token`
(required, secret), `name` (optional). `validate_token()` gates submission;
errors → `cannot_connect` / `invalid_auth`. Reauth flow re-prompts token only.

Options: scan interval; enable/disable each matching strategy;
`allow_ambiguous_match` default. Slot map is edited via services (not the options UI in V1).

## 8. Errors & logging

- Network → `SpoolyTrackerConnectionError` → `UpdateFailed` / `HomeAssistantError`.
- 401/403 → `SpoolyTrackerAuthError` → `ConfigEntryAuthFailed` → reauth.
- Other non-2xx → `SpoolyTrackerApiError` with status+message.
- Logs: one `info` on setup, `debug` per request, `warning` only on unresolved/ambiguous.
  No per-poll info spam.

## 9. Testing

`matching.py` gets unit tests (all 5 strategies, ambiguity, disabled strategies).
`api.py` payload builder (notes formatting, int coercion) unit-tested. Config-flow
happy path + invalid auth. (HA test harness optional for V1; logic is isolated so
tests run without a running HA.)

## 10. Out of scope for V1 (→ V2)

Unresolved-consumption queue with replay; mobile actionable notification to pick a
spool; multi-material per job; AMS auto-detection; active-spool sync back to
SpoolyTracker; low-stock alerts as HA binary_sensors/notifications; projects entities
(pending API). Captured in README "V2".
