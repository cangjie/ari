# Boston Summer Street Tour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the 53-record Boston Summer Street collection with sourced photos, two fixed-endpoint walking itineraries, GPS vicinity guidance, and shared Web/Android delivery.

**Architecture:** Normalize the existing inventory and V3 ratings into the audited collection package already consumed by `tour_collection_build.py`. Add Boston-specific media and experience manifests while extending the generic experience builder and UI to support a fixed set of starts per itinerary. Generate a static tour JSON and route assets, then publish through the existing catalog and server fast-forward workflow.

**Tech Stack:** Python 3.12, openpyxl, existing Ariadne V3/audit helpers, OpenStreetMap XML/JSON snapshots, Pillow, vanilla HTML/CSS/JavaScript, pytest, Chrome DevTools browser checks, Git/SSH deployment.

**Spec:** `docs/superpowers/specs/2026-11-03-boston-summer-st-tour-design.md`

## Global Constraints

- Tour key is exactly `boston_summer_st`; keep all 53 bilingual records and current tier counts S0 / A12 / B11 / C30.
- Web and the existing Android App consume the same server catalog and static data; do not rebuild the APK.
- Do not write the production business database, change Nginx, or modify existing destinations' content.
- GPS uses sourced public-street references and the existing accuracy/re-entry rules; it is not turn-by-turn navigation.
- Photos must match their own subject and record URL, author, license, caption, original/published hashes, and dimensions; do not generate, crop subjects, remove watermarks, or borrow adjacent-place photos.
- Food-route tiers remain cultural visit priority, not food/service ratings; live business, ticket, and access state stays explicitly unverified.
- Pure sightseeing starts near Park Street and ends near Courthouse; sightseeing plus food starts near Downtown Crossing and ends near Silver Line Way. Each theme has one fixed start.
- Required food stops are Tatte, High Street Place, Flour, Row 34, Coquette, and Harpoon; Trillium, M.J. O'Connor's, and Legal Harborside are optional and do not affect routing or GPS alerts.

## Review Focus

- A route step that maps to an OSM feature but snaps to a private/indoor path must fail instead of creating a shortcut; Task 4 tests all route way IDs against `StreetGraph.ways`.
- An optional restaurant must never appear among required route steps, GPS places, or route time totals; Task 4 asserts the three optional IDs are excluded.
- A photo whose manifest identity, published filename, or SHA differs from its record must fail the build; Task 3 exercises each binding.
- A fixed-start itinerary must show only its own start in the UI while existing Nanluo four-start themes remain unchanged; Tasks 4 and 5 cover both data and browser behavior.
- Catalog or public assets served stale after deployment must be detected by byte-for-byte comparison on both HTTPS domains; Task 6 performs exact public checks.

---

### Task 1: Audited Boston collection package

**Files:**
- Create: `utils/import_data/boston_summer_st_package.py`
- Create: `utils/import_data/test_boston_summer_st_package.py`
- Create: `utils/import_data/boston_summer_st_source_capture.json`
- Create: `utils/import_data/boston_summer_st_site_data.json`
- Create: `utils/import_data/boston_summer_st_peer_groups.json`
- Create: `utils/import_data/boston_summer_st_audit_source_data.json`
- Create: `utils/import_data/boston_summer_st_audit1_slim.jsonl`
- Create: `utils/import_data/boston_summer_st_audit_manifest.json`
- Create: `utils/import_data/boston_summer_st_translations.json`
- Create: `utils/import_data/boston_summer_st_final.json`
- Create: `utils/import_data/boston_summer_st_verification_report.json`
- Modify: `utils/import_data/boston_summer_st_rate.py`
- Test: `utils/import_data/test_boston_summer_st_package.py`

**Interfaces:**
- Consumes: `boston_summer_st_list.rows`, `boston_summer_st_ratings.json`, and the unique HTTPS source URLs already bound to the inventory.
- Produces: the standard `tour_collection_build.build("boston_summer_st", config)` package contract with numeric `source_seq`, stable lowercase identity keys, bilingual values, complete source/audit coverage, and `state == "独立审计完成"`.

- [ ] **Step 1: Write the failing package-contract tests**

Assert 53 unique stable identities; exact tier counts; one or more saved source records per row; capture text and retrieval method; matching input/rating/audit hashes; 53 independent audit rows; bilingual text coverage; shops marked as `特色商铺`; and no database-write flag.

- [ ] **Step 2: Run the package test and verify RED**

Run: `utils/import_data/.venv/bin/pytest utils/import_data/test_boston_summer_st_package.py -q`

Expected: FAIL because `boston_summer_st_package.py` and normalized package files do not exist.

- [ ] **Step 3: Implement source capture and deterministic normalization**

Implement `capture_sources()`, `build_site_data()`, `build_translations()`, and `build_final()` in `boston_summer_st_package.py`. Preserve HTTP body/extracted text/retrieval method separately; do not label search excerpts as HTTP responses. Update `boston_summer_st_rate.py` to emit the standard `peer_groups.json` and ratings hash fields without changing existing scores.

- [ ] **Step 4: Run independent slim audit and build its manifest**

Use the existing Claude Sonnet 5 medium audit path on all 53 rows with saved source text. Save provider outputs before validation, keep audit results separate from ratings, and resolve factual or identity findings in the package while retaining disposition evidence.

- [ ] **Step 5: Run package test and full source verification GREEN**

Run: `utils/import_data/.venv/bin/pytest utils/import_data/test_boston_summer_st_package.py -q`

Expected: PASS with 53 records and S0/A12/B11/C30.

- [ ] **Step 6: Commit**

Commit message: `data(tour): audit Boston Summer Street collection`

### Task 2: Base collection publishing contract

**Files:**
- Create: `utils/import_data/boston_summer_st_tour_data.py`
- Create: `web_api/tests/test_boston_summer_st_tour.py`
- Modify: `utils/import_data/tour_collection_build.py`
- Create: `web_api/tour/data/boston_summer_st.json`

**Interfaces:**
- Consumes: Task 1's standard package files.
- Produces: a collection-mode tour JSON with 53 places/stops, configurable Boston area translations, shop boundaries, source links, ratings, audit notes, and no map/routes until media is added.

- [ ] **Step 1: Write failing collection identity and content tests**

Add tests asserting all package rows appear once, IDs/names/descriptions/ratings/sources match, tier counts are exact, shops retain address and live-status boundaries, and question-answer material contains the same review boundaries.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py -q`

Expected: FAIL because the Boston tour config and generated JSON do not exist.

- [ ] **Step 3: Make collection areas and platform references configurable**

Modify `tour_collection_build.build(key, config)` to use `config.AREA_EN` and a Boston `platform_reference()` when provided, while retaining the existing Nanluo defaults. Add `boston_summer_st_tour_data.py` with card/opening/planning copy and collection mode.

- [ ] **Step 4: Generate the base Boston JSON and verify GREEN**

Run: `utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum boston_summer_st`

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py tests/test_collection_tour.py -q`

Expected: PASS; existing Nanluo tests remain green.

- [ ] **Step 5: Commit**

Commit message: `feat(tour): add Boston Summer Street collection`

### Task 3: Sourced map and photo coverage

**Files:**
- Create: `utils/import_data/boston_summer_st_osm_response.xml`
- Create: `utils/import_data/boston_summer_st_osm_data.json`
- Create: `utils/import_data/boston_summer_st_tour_media.json`
- Create: `utils/import_data/boston_summer_st_tour_photos.json`
- Create: `utils/import_data/boston_summer_st_photo_build.py`
- Create: `web_api/tour/img/boston_summer_st/<seq>.jpg` for every required route/photo record
- Modify: `utils/import_data/boston_summer_st_tour_data.py`
- Modify: `web_api/tests/test_boston_summer_st_tour.py`

**Interfaces:**
- Consumes: Task 2's 53 places and saved OSM snapshot.
- Produces: `MEDIA_MANIFEST`, a browsable map projection, sourced positions for route/main records, matching photo files and photo metadata, and a cover photo.

- [ ] **Step 1: Add failing OSM and photo-binding tests**

Assert raw/normalized OSM hashes, every route candidate has a sourced position, every required photo record has its own file and matching identity/hash/source/license/caption/dimensions, no non-route record borrows a parent/neighbor image, and all images decode.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py -q`

Expected: FAIL because Boston media manifests and image files do not exist.

- [ ] **Step 3: Capture and normalize the OSM corridor**

Save the official OSM response covering Park Street through Silver Line Way, normalize public roads/paths/water/parks/named buildings, bind each route candidate by OSM feature ID and position basis, and reject missing or changed OSM names.

- [ ] **Step 4: Select, inspect, and build photos**

Prefer official reusable images or explicitly licensed Wikimedia Commons files. Visually inspect every selected original, record author/license/source and exact subject, then publish orientation-corrected, proportionally resized files with deterministic hashes.

- [ ] **Step 5: Generate tour data and verify GREEN**

Run: `utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum boston_summer_st`

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py -q`

Expected: PASS with a map, cover, and complete required photo bindings.

- [ ] **Step 6: Commit**

Commit message: `feat(tour): add Boston map and sourced photos`

### Task 4: Fixed-start itineraries and GPS guidance

**Files:**
- Create: `utils/import_data/boston_summer_st_experience_data.py`
- Create: `utils/import_data/boston_summer_st_experience.json`
- Modify: `utils/import_data/tour_collection_experience.py`
- Modify: `utils/import_data/boston_summer_st_tour_data.py`
- Modify: `web_api/tour/app.js`
- Modify: `web_api/tests/test_boston_summer_st_tour.py`
- Modify: `web_api/tests/test_collection_tour.py`

**Interfaces:**
- Consumes: Task 3's OSM graph and sourced position records.
- Produces: `theme.start_stations: list[str]`, exactly one route variant per Boston theme, two `itineraries`, GPS public-street points for required steps, and UI start selection limited to each theme's variants. Existing manifests without `start_stations` retain all-station behavior.

- [ ] **Step 1: Write failing fixed-start and route-contract tests**

Assert two exact themes, one variant each, fixed start/end station IDs, required step order, optional food IDs excluded from steps/GPS, all way IDs public, distances equal WGS-84 path sums, time arithmetic, photo coverage, and Nanluo still has four variants per theme.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py tests/test_collection_tour.py -q`

Expected: FAIL because fixed-start filtering and Boston experience data do not exist.

- [ ] **Step 3: Extend the generic experience builder**

In `tour_collection_experience.augment`, use `theme.get("start_stations", all_station_ids)` to build variants and reject unknown/empty lists. Keep current behavior byte-compatible for Nanluo manifests.

- [ ] **Step 4: Extend the theme UI for available starts**

Add a small helper in `app.js` that derives visible start stations from a theme's variants. Hide or disable the selector when only one variant exists; do not alter existing four-start themes.

- [ ] **Step 5: Define and generate the two Boston experiences**

Create the approved stop sequences, fixed Park Street/Courthouse and Downtown Crossing/Silver Line Way connections, stay estimates, optional food lists, access notes, and MBTA/OSM station sources. Generate public-road paths and GPS vicinity points with existing thresholds.

- [ ] **Step 6: Run focused and full pytest GREEN**

Run: `utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum boston_summer_st --check`

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest -q`

Expected: PASS; Boston has two one-variant themes and existing destination tests remain green.

- [ ] **Step 7: Commit**

Commit message: `feat(tour): add Boston themed GPS walks`

### Task 5: Standalone maps and browser acceptance

**Files:**
- Modify: `utils/import_data/tour_itinerary_maps.py`
- Create: `utils/import_data/boston_summer_st_itinerary_maps.json`
- Create: `web_api/tour/img/boston_summer_st/route-sightseeing-park.svg`
- Create: `web_api/tour/img/boston_summer_st/route-sightseeing-park.png`
- Create: `web_api/tour/img/boston_summer_st/route-food-downtown.svg`
- Create: `web_api/tour/img/boston_summer_st/route-food-downtown.png`
- Modify: `web_api/tests/tour_browser_check.mjs`
- Modify: `web_api/tests/test_boston_summer_st_tour.py`

**Interfaces:**
- Consumes: Task 4 itinerary paths, ordered steps, and fixed endpoints.
- Produces: two SVG/PNG route-map pairs bound by hash to the generated JSON and browser scenarios covering list/map/theme/GPS behavior.

- [ ] **Step 1: Add failing standalone-map and browser scenario checks**

Assert each theme's SVG/PNG exists, hashes match, markers follow route order, endpoints are S/E, path is fully visible, and the browser can open Boston, decode all required photos, switch both themes, start GPS, receive a vicinity alert, return to the list, and preserve existing Nanluo behavior.

- [ ] **Step 2: Run tests/scenarios and verify RED**

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest tests/test_boston_summer_st_tour.py -q`

Run: `node web_api/tests/tour_browser_check.mjs boston_collection boston_routes boston_gps`

Expected: FAIL because Boston route map assets and scenarios are not complete.

- [ ] **Step 3: Generate responsive route maps and complete scenarios**

Use the generic itinerary map renderer for each one-variant theme. Keep route lines, markers, labels, and endpoint visibility within the mobile view box. Implement the three named browser scenarios without changing production interaction rules.

- [ ] **Step 4: Run focused browser and regression GREEN**

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest -q`

Run: `node web_api/tests/tour_browser_check.mjs boston_collection boston_routes boston_gps collection collection_host live photos`

Expected: PASS with all images decoded and no console errors.

- [ ] **Step 5: Commit**

Commit message: `test(tour): verify Boston routes and GPS flow`

### Task 6: Catalog publication, documentation, and public deployment

**Files:**
- Modify: `web_api/tour/catalog.json`
- Create: `utils/import_data/boston_summer_st_release_verify.py`
- Create: `utils/import_data/boston_summer_st_local_report.json`
- Create after deployment: `utils/import_data/boston_summer_st_public_report.json`
- Create: `docs/BOSTON_SUMMER_ST_DATA.md`

**Interfaces:**
- Consumes: all generated data, image, and route assets from Tasks 1-5.
- Produces: catalog entry, reproducible local/public release evidence, committed documentation, pushed master commit, and exact deployed assets on both tour domains.

- [ ] **Step 1: Write failing release verification**

The verifier must check catalog order and uniqueness, 53 records, tier counts, photo/map hashes, two route variants, GPS points, no database/APK/Nginx changes, and byte-for-byte public assets on both domains when `--public` is given.

- [ ] **Step 2: Run local verifier and verify RED**

Run: `utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_release_verify.py`

Expected: FAIL until catalog/documentation and all final assets are registered.

- [ ] **Step 3: Add catalog entry and release documentation**

Append `boston_summer_st` to the server catalog. Document sources, audit, tier boundary, photo licensing, map/GPS behavior, route stops, commands, and unverified field/device conditions.

- [ ] **Step 4: Run the full local release gate GREEN**

Run: `utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum boston_summer_st --check`

Run: `cd web_api && ../utils/import_data/.venv/bin/pytest -q`

Run: `node web_api/tests/tour_browser_check.mjs`

Run: `utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_release_verify.py`

Expected: all commands PASS and local report records zero production posts, no APK rebuild, and no Nginx/database change.

- [ ] **Step 5: Commit and push the release**

Commit message: `feat(tour): publish Boston Summer Street guide`

Push the reviewed fast-forward history to `origin/master`, preserving the three unrelated Android Gradle modifications in the original worktree.

- [ ] **Step 6: Deploy static content and verify both public domains**

On `ubuntu@44.207.251.65`, reuse the SSH control connection, confirm the server worktree is clean and at the expected base, then run `git pull --ff-only`. Do not restart services because only static tour content changed.

Run public asset verification for `https://tour.snowmeet.top` and `https://tour.arimuseum.org`, then run the named browser scenarios against HTTPS. Use read-only GET for question lists and send no production questions.

Expected: catalog/data/photos/route assets are HTTPS 200 and byte-identical on both domains; both routes, GPS simulation, existing destinations, and read-only QA lists pass.

- [ ] **Step 7: Commit and push the public report**

Commit message: `docs(tour): record Boston Summer Street public acceptance`
