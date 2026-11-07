# Greater Boston 景点导览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a sourced, bilingual, regional Boston attractions collection with locally walkable route themes, maps and GPS vicinity points, while preserving existing tours.

**Architecture:** Build a new collection package with stable identities, saved first-party evidence, V3 cultural/visit-priority ratings, translations and an independent content audit. Reuse the existing collection, media, experience and itinerary-map builders to publish the new `boston_area` JSON from the server catalog; keep each route local to one neighborhood or day-trip region, with transit connectors represented separately.

**Tech Stack:** Python 3, JSON/JSONL, the existing V3 and tour collection builders, OSM public walking data, MBTA GTFS, existing static HTML/CSS/JS, and `openpyxl` for the review workbook. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-06-boston-metro-guide-design.md`

## Global Constraints

- Cover all Boston neighborhoods and the specified Cambridge, Salem, Concord and Lexington areas; include all seven requested content types.
- Treat `boston_area` as a new guide; preserve the published `boston_summer_st` guide and every other destination.
- Keep the complete location list independent of which locations have verified map or GPS positions.
- Use direct sources and retain captured text; a search snippet is not a captured source page.
- Use V3 only for cultural/visit priority; do not rate restaurant taste, service, price or current operation.
- Distinguish public access, exterior-only viewing, tickets, appointments and seasonal conditions; date time-sensitive checks.
- Use public, sourced street geometry for walking paths and GPS vicinity points; do not present a reference point as an entrance.
- Do not write the business database, change Nginx, alter unrelated destinations, or modify/rebuild the Android app.
- Prepare a reviewable local result; production deployment requires a separately agreed time.
- Do not add or run tests unless the user explicitly asks for testing or verification.

## File Structure

- `utils/import_data/boston_area_list.py` — curated bilingual inventory rows and workbook generator.
- `utils/import_data/boston_area_source_capture.py` and `boston_area_v3_*` — saved evidence, translations, rating inputs/results, peer groups, audit and final package inputs.
- `utils/import_data/boston_area_tour_data.py` — collection display metadata and builder settings.
- `utils/import_data/boston_area_osm_capture.py`, `boston_area_osm_raw.json`, `boston_area_osm.json`, `boston_area_mbta_*.json` — regional public-walk graph, place positions and transit source records.
- `utils/import_data/boston_area_media.json`, `boston_area_photos.json`, and `utils/import_data/boston_area_experience.json` — verified position/photo bindings, route themes and GPS policy.
- `utils/import_data/boston_area_itinerary_maps.json` — generated route-map checksums and bindings.
- `web_api/tour/data/boston_area.json` and `web_api/tour/img/boston_area/` — generated visitor data, licensed photos and theme map assets.
- `web_api/tour/catalog.json` — server-controlled card ordering and availability.
- `docs/BOSTON_AREA_DATA.md` — scope, sources, review boundaries and local build instructions.

## Review Focus

- Duplicate identities across the Freedom Trail, Boston Summer Street and regional site lists — Task 1 keeps canonical entity IDs and parent/related links.
- Current access claims for campuses, historic houses, museums, parks and restaurants — Task 2 binds claims to dated captured sources and reviewer dispositions.
- Regional day-trip stops disconnected by transit or season — Task 4 keeps transit legs, local walking legs and seasonal service notes separate.
- OSM snapping to a private way, a campus interior, an entrance that was never sourced, or the wrong branch — Tasks 4 and 5 retain way IDs, source references and identity-bound photo metadata.
- Sparse or geographically distant points on the Greater Boston overview — Task 3 keeps it an overview, while Task 4 creates local route maps for each walk.

---

### Task 1: Curate the regional inventory and workbook

**Files:**
- Create: `utils/import_data/boston_area_list.py`
- Create: `utils/import_data/exports/波士顿及周边景点_双语清单.xlsx` (ignored review output)

**Interfaces:**
- Consumes: user-approved geographic scope and seven requested categories; first-party municipal, museum, university, park, NPS and operator sources.
- Produces: `rows` in the same shape as `boston_summer_st_list.rows`, with stable lowercase `id`, `zone`, `kind`, `zh`, `en`, `zh_desc`, `en_desc`, `address`, `relation`, `access`, `source`, `source_name`, and `note` fields. Each physical entity appears once; sites inside an overall trail are linked by relation rather than duplicated as identities.

- [ ] Define compact category values for universities, museums, heritage, parks, architecture, streets and dining; use `zone` for city/neighborhood or day-trip region.
- [ ] Populate only visitor-relevant candidates with a cited source and an explicit public-access note; include Harvard, MIT, MFA, PEM, Concord and Lexington anchors.
- [ ] Record excluded/uncertain candidates in editor notes rather than filling missing facts from category assumptions.
- [ ] Generate the bilingual workbook with separate columns for identity, names, category, area, source, access boundary and review note.
- [ ] Manually reconcile the workbook count against `rows`, confirm unique IDs and inspect representative entries from every requested category and region.

**Deliverable:** A curated, deduplicated inventory workbook and source-controlled rows; no claim of exhaustive coverage.

### Task 2: Capture evidence, translate, rate and audit the collection

**Files:**
- Create: `utils/import_data/boston_area_source_capture.py`
- Create: `utils/import_data/boston_area_v3_source_capture.json`
- Create: `utils/import_data/boston_area_v3_site_data.json`
- Create: `utils/import_data/boston_area_v3_translations.json`
- Create: `utils/import_data/boston_area_v3_rating_input.json`
- Create: `utils/import_data/boston_area_v3_peer_groups.json`
- Create: `utils/import_data/boston_area_v3_rating_stage1.jsonl`
- Create: `utils/import_data/boston_area_v3_rating_stage2.jsonl`
- Create: `utils/import_data/boston_area_v3_rating_stage3.jsonl`
- Create: `utils/import_data/boston_area_v3_ratings.json`
- Create: `utils/import_data/boston_area_v3_audit_source_data.json`
- Create: `utils/import_data/boston_area_v3_audit_manifest.json`
- Create: `utils/import_data/boston_area_v3_audit_request.json`
- Create: `utils/import_data/boston_area_v3_audit_results.json`
- Create: `utils/import_data/boston_area_v3_audit1_slim.jsonl`
- Create: `utils/import_data/boston_area_v3_final.json`
- Create: `utils/import_data/boston_area_v3_verification_report.json`

**Interfaces:**
- Consumes: Task 1 rows.
- Produces: the input contract consumed by `tour_collection_build.build(key, config)`: a final package, ratings with the exact inventory-input hash, per-source evidence/captured text, translations, peer groups, audit manifest/source files and one audit row per released record.

- [ ] Capture the official or institution/operator page actually used for each visitor-facing claim; save URL, title, retrieval method, retrieval date and text, and label any unavailable/non-HTTP content honestly.
- [ ] Bind each evidence quote to its exact source record and ensure each inventory row has enough evidence for its visitor description, access note and identity.
- [ ] Create Chinese/English translations without changing source meanings; preserve names as used by institutions and add aliases for common visitor search terms.
- [ ] Build the V3 rating input and peer groups; calculate and preserve the exact source/input hashes before rating.
- [ ] Run the repository's current V3 rating and independent slim content-audit workflow once the user-approved execution approach is selected; do not change the algorithm or mix audit corrections into ratings silently.
- [ ] Resolve factual, identity and visitor-risk findings in the source rows while keeping the original audit result and an explicit disposition.
- [ ] Produce the `独立审计完成` package only after all source, translation, rating and audit coverage refer to matching hashes.

**Deliverable:** A reproducible V3 package with source-to-description, rating and audit identity coverage.

### Task 3: Build the base Boston-area collection package

**Files:**
- Create: `utils/import_data/boston_area_tour_data.py`
- Create: provisional generated `web_api/tour/data/boston_area.json`

**Interfaces:**
- Consumes: Task 2's `boston_area_v3_*` package.
- Produces: `boston_area_tour_data.py` constants consumed by `tour_collection_build.build('boston_area', config)`, which returns `(data: dict, warnings: list[str])`; generated JSON uses `mode='collection'`, complete `places`/`stops`, `routes=[]`, `default_route='none'`, `map_mode='browse'`, provenance hashes and `business_database_written=false`.

- [ ] Configure `PACKAGE_PREFIX='boston_area_v3'`, `RATING_INVENTORY_FILE`, `REQUIRE_VERIFIED_EVIDENCE`, `AREAS`, bilingual name/card/opening/planning text and source-bound shop policy.
- [ ] Generate the complete base collection JSON through `tour_collection_build.build('boston_area', config)`; do not hand-edit generated JSON.
- [ ] Inspect a sample from every zone/category for stable identity, correct bilingual text, access notes and no invented dwell time.

**Deliverable:** A complete Boston-area collection JSON with display metadata, ready for regional media and route augmentation.

### Task 4: Define transit-linked local walks, route maps and GPS points

**Files:**
- Create: `utils/import_data/boston_area_osm_capture.py`
- Create: `utils/import_data/boston_area_osm_raw.json`
- Create: `utils/import_data/boston_area_mbta_capture.py`
- Create: `utils/import_data/boston_area_mbta_stops.json`
- Create: `utils/import_data/boston_area_street_references.json`
- Create: `utils/import_data/boston_area_media.json`
- Create: `utils/import_data/boston_area_experience.json`
- Modify: `utils/import_data/boston_area_tour_data.py` to bind the verified media and experience manifests.

**Interfaces:**
- Consumes: Task 3 collection stops with coordinates; saved public OSM walking ways; MBTA stop/entrance IDs and GTFS capture.
- Produces: `EXPERIENCE_MANIFEST` with `stations`, `themes[].steps`, optional shops, local start/end station IDs, public street names, transit sources and GPS policy; `tour_collection_experience.augment(data, config)` adds itinerary variants and `navigation`; `tour_itinerary_maps.py --museum boston_area` writes standalone SVG/PNG route maps and hash manifest.

- [ ] Finalize local route themes from the approved candidates only after identity, public access and route connectivity are sourced; use local Boston/Cambridge/Salem/Concord-Lexington modules rather than cross-region walking routes.
- [ ] Keep MBTA, commuter rail, ferry and other transit connectors distinct from walk legs; record seasonal service and the date of each transit reference.
- [ ] Snap every stop to an explicitly named public way or verified source node; record the OSM way/node and segment fraction; reject private, indoor, paid-campus and inaccessible shortcuts.
- [ ] Set stay minutes as labeled estimates; do not count meals, lines, museum visits, tickets or transit time as if measured walk time.
- [ ] Generate independent local route maps so Boston overview scale does not determine the legibility of Salem and Concord/Lexington walks.
- [ ] Enable GPS alerts only for verified route reference points; keep complete catalogue records even if they have no GPS point.
- [ ] Review every route's start/end, way IDs, transit notes, distance arithmetic, position identity and GPS vicinity note against its saved source.
- [ ] If the approved route set cannot fit the existing collection/media/experience contract, stop and update the design before changing shared builders or the front-end.

**Deliverable:** Regional walk themes with saved public street/transit evidence and sourced GPS vicinity points, separate from inter-city travel legs.

### Task 5: Select and bind licensed destination photos

**Files:**
- Create: `utils/import_data/boston_area_photos.py`
- Create: `utils/import_data/boston_area_photo_candidates.json`
- Create: `utils/import_data/boston_area_photo_review.json`
- Create: `utils/import_data/boston_area_photo_license_check.json`
- Create: `utils/import_data/boston_area_photos.json`
- Create: `utils/import_data/boston_area_photo_manifest.json`
- Create: `web_api/tour/img/boston_area/<seq>.jpg` for the verified photo bindings

**Interfaces:**
- Consumes: Task 4's final route stops and identity keys; official image sources or clearly licensed Wikimedia Commons originals.
- Produces: photo manifest rows bound by `seq` and `identity_key`, with source URL, author, license, caption, source-file hash and published JPEG hash; collection builder attaches these images to the matching stop and selects a verified `cover_seq`.

- [ ] Candidate photos only for route anchors, key institutions and representative regional places; do not set a coverage quota.
- [ ] View each original image; reject a wrong branch, neighboring attraction, ambiguous scene or unclear license.
- [ ] Preserve author and license metadata; make only orientation correction and proportional resizing/encoding, with no watermark removal or generative edits.
- [ ] Bind only photos whose subject, identity, source and published-file hash match the inventory record; keep other entries without photos.

**Deliverable:** A small, relevant photo set with per-image provenance and a guide cover.

### Task 6: Build final maps, update the catalog and document the local handoff

**Files:**
- Create: generated `web_api/tour/data/boston_area.json`
- Create: generated `utils/import_data/boston_area_itinerary_maps.json`
- Create: `web_api/tour/img/boston_area/route-<theme>-<start>.svg` and `.png`
- Modify: `web_api/tour/catalog.json`
- Create: `docs/BOSTON_AREA_DATA.md`

**Interfaces:**
- Consumes: Tasks 1–5 inventories, hashes, route/photo manifests and explicit unresolved items.
- Produces: final collection JSON and route-map assets plus a maintenance handoff with scope, source selection, package/build entrypoints and boundaries between local completion and production publication.

- [ ] Run `python utils/import_data/tour_build.py --museum boston_area` to generate the final guide data.
- [ ] Run `python utils/import_data/tour_itinerary_maps.py --museum boston_area` to generate each route's standalone SVG/PNG assets and checksum manifest.
- [ ] Add one `boston_area` catalog entry while preserving all existing keys, order and publication states.
- [ ] Document verified geographic coverage, record counts, tier distribution, date-sensitive access caveats, route estimates, image licensing and unverified field/Android conditions.
- [ ] List unresolved source gaps, routes or photos rather than implying they were completed.
- [ ] Prepare deployment impact notes for a later decision; do not push, deploy or change server state as part of the local build.
- [ ] Leave `AGENTS.md`, `PROGRESS.md` and the Copilot copy for the explicit end-work workflow.

**Deliverable:** A reviewable local guide package and explicit publication handoff.

## Execution Notes

- Do not begin these tasks until the user has reviewed this plan and chosen an execution method.
- The current working tree contains unrelated Android Gradle edits and untracked Boston Summer Street files that block a fast-forward. Preserve them; use an isolated worktree based on the fetched `origin/master` before implementation, or first reconcile the overlapping files without discarding local content.
- No test files or test runs are included under the current instruction; if the user later asks for verification, add verification scope explicitly before running it.
