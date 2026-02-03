# Urbix Cadastre & Planning API — Technical Plan
**Date:** 2026-02-03
**For:** Tonight's dev session with Juliano
**Status:** DRAFT — ready for review

---

## 1. What We're Building

An API that answers **"What can I build on this lot?"** for any property in Queensland.

**Input:** Address or Lot/Plan reference
**Output:** Cadastre data + zoning + planning rules + buildability summary

Think of it as **Geoscape's data + an engineer's brain**, wrapped in an API.

---

## 2. Data Sources (All FREE — QLD Government)

### ✅ Confirmed Available (ArcGIS REST — live, tested)

| Dataset | Service | Update Freq | What It Gives Us |
|---------|---------|-------------|------------------|
| **DCDB Cadastral Parcels** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/4` | **Nightly** | Lot boundaries, Lot/Plan refs, parcel type (Base/Easement/Strata/Volumetric), area |
| **Addresses** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/0` | **Nightly** | Geocoded addresses → link address to parcel |
| **Properties** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/50` | Nightly | Property aggregations (multi-lot properties) |
| **Tenure** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/13` | Nightly | Freehold, leasehold, state land |
| **Land Use** | `PlanningCadastre/LandUse/FeatureServer/0` | Periodic | Current land use classification (ALUMC) |
| **LGA Boundaries** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/20` | Quarterly | Which council → which planning scheme |
| **Locality Boundaries** | `PlanningCadastre/LandParcelPropertyFramework/MapServer/19` | Quarterly | Suburb/locality |
| **Priority Development Areas** | `PlanningCadastre/PriorityDevelopmentAreas/MapServer` | As needed | Special planning areas |
| **State Development Areas** | `PlanningCadastre/StateDevelopmentAreas/MapServer` | As needed | State-significant development zones |
| **Residential Land Supply** | `PlanningCadastre/ResidentialLandSupply/MapServer` | Periodic | Development potential areas |
| **Coastal Management** | `PlanningCadastre/CoastalManagement/MapServer` | As needed | Coastal overlays |
| **Areas of Regional Interest** | `PlanningCadastre/AreasOfRegionalInterest/MapServer` | As needed | Regional planning overlays |

**Base URL:** `https://spatial-gis.information.qld.gov.au/arcgis/rest/services/`

### 🔍 Need to Locate (Phase 2)

| Dataset | Likely Source | Priority |
|---------|--------------|----------|
| **Planning Scheme Zones** | QPlan / individual council WFS | HIGH — the core "what zone is this?" question |
| **Planning Overlays** | QPlan / council mapping | HIGH — flood, heritage, bushfire, character |
| **Building Heights/FSR** | Planning scheme PDFs → AI extraction | MEDIUM |
| **Setback Rules** | Planning scheme tables → AI extraction | MEDIUM |
| **Flood Maps** | FloodCheck / council WMS | HIGH |
| **Bushfire Zones** | QFES mapping services | MEDIUM |
| **Title References** | Titles Queensland API ($27/search) | LOW — already doing this for TitleFinder |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│                    URBIX API                         │
│                  (FastAPI + Python)                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  /lookup?address=123+Main+St+Brisbane                │
│  /lookup?lot=3&plan=RP12345                          │
│  /zoning?lat=-27.47&lng=153.02                       │
│  /buildability?lot=3&plan=RP12345                    │
│  /report?address=123+Main+St+Brisbane   (PDF)        │
│                                                      │
├─────────────────────────────────────────────────────┤
│                  PROCESSING LAYER                    │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ Geocoder │ │ Spatial  │ │  Planning Rules      │ │
│  │ (address │ │ Query    │ │  Engine (AI + rules  │ │
│  │  → lat/  │ │ (PostGIS │ │  for zone→buildable) │ │
│  │   lng)   │ │  + cache)│ │                      │ │
│  └──────────┘ └──────────┘ └──────────────────────┘ │
│                                                      │
├─────────────────────────────────────────────────────┤
│                  DATA LAYER                          │
│                                                      │
│  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ PostGIS   │  │ Redis    │  │ QLD ArcGIS       │  │
│  │ (cached   │  │ (hot     │  │ (live source     │  │
│  │  parcels, │  │  query   │  │  — fallback)     │  │
│  │  zones)   │  │  cache)  │  │                  │  │
│  └───────────┘  └──────────┘  └──────────────────┘  │
│                                                      │
├─────────────────────────────────────────────────────┤
│              NIGHTLY SYNC PIPELINE                   │
│                                                      │
│  QLD ArcGIS → Download → Transform → PostGIS Load   │
│  (Runs 2am AEST, catches nightly DCDB updates)      │
└─────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **API** | FastAPI (Python) | Fast, async, auto-docs, Juliano learning Python |
| **Database** | PostgreSQL + PostGIS | Industry standard for spatial, free, powerful |
| **Cache** | Redis | Hot query cache, rate limiting |
| **Spatial ETL** | Python + GDAL/OGR + Fiona | Read ArcGIS REST, transform, load to PostGIS |
| **AI Layer** | Claude API | Parse planning rules from PDFs to structured data |
| **Hosting** | Railway / Fly.io / VPS | Start cheap ($10-20/mo), scale later |
| **Map Tiles** | MapLibre GL JS (frontend) | Free, open-source Mapbox alternative |

---

## 5. Database Schema (MVP)

```sql
-- Core spatial tables (populated by nightly sync)

CREATE TABLE parcels (
    id SERIAL PRIMARY KEY,
    lot VARCHAR(20),
    plan_number VARCHAR(20),
    lot_plan VARCHAR(40) UNIQUE,  -- "3/RP12345"
    parcel_type VARCHAR(30),       -- Base, Easement, Strata, Volumetric
    cover_type VARCHAR(30),        -- Base, Easement, Strata, Volumetric
    tenure VARCHAR(50),            -- Freehold, Leasehold, State Land
    area_sqm NUMERIC,
    lga VARCHAR(100),              -- Local Government Area
    locality VARCHAR(100),         -- Suburb/locality
    geom GEOMETRY(MultiPolygon, 4283),  -- GDA94 (native QLD projection)
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT idx_parcels_lotplan UNIQUE (lot_plan)
);
CREATE INDEX idx_parcels_geom ON parcels USING GIST (geom);
CREATE INDEX idx_parcels_lot_plan ON parcels (lot, plan_number);

CREATE TABLE addresses (
    id SERIAL PRIMARY KEY,
    full_address TEXT,
    unit_number VARCHAR(20),
    street_number VARCHAR(20),
    street_name VARCHAR(100),
    street_type VARCHAR(20),
    locality VARCHAR(100),
    postcode VARCHAR(10),
    parcel_id INTEGER REFERENCES parcels(id),
    geom GEOMETRY(Point, 4283),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_addresses_geom ON addresses USING GIST (geom);
CREATE INDEX idx_addresses_fulltext ON addresses USING GIN (to_tsvector('english', full_address));

CREATE TABLE zones (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(50),         -- e.g., "Low density residential"
    zone_short VARCHAR(20),        -- e.g., "LDR"
    planning_scheme VARCHAR(200),  -- e.g., "Sunshine Coast Planning Scheme 2014"
    lga VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4283),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_zones_geom ON zones USING GIST (geom);

CREATE TABLE overlays (
    id SERIAL PRIMARY KEY,
    overlay_type VARCHAR(100),     -- Flood, Heritage, Bushfire, Character, etc.
    overlay_name VARCHAR(200),
    overlay_code VARCHAR(50),
    planning_scheme VARCHAR(200),
    lga VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4283),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_overlays_geom ON overlays USING GIST (geom);

-- Planning rules (populated by AI extraction from planning scheme PDFs)
CREATE TABLE planning_rules (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(50),
    lga VARCHAR(100),
    planning_scheme VARCHAR(200),
    -- Buildability rules
    max_height_m NUMERIC,
    max_storeys INTEGER,
    min_lot_size_sqm NUMERIC,
    max_site_cover_pct NUMERIC,    -- site coverage %
    min_frontage_m NUMERIC,
    front_setback_m NUMERIC,
    side_setback_m NUMERIC,
    rear_setback_m NUMERIC,
    max_dwelling_density VARCHAR(100),  -- e.g., "1 per 400sqm"
    -- Use categories
    accepted_uses TEXT[],           -- uses that are "accepted development"
    assessable_uses TEXT[],         -- uses requiring council assessment
    prohibited_uses TEXT[],         -- uses that are not permitted
    -- Raw source
    source_document TEXT,           -- PDF filename
    source_section TEXT,            -- Section reference
    ai_confidence NUMERIC,          -- 0-1 confidence from AI extraction
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Materialized view for fast lookups
CREATE MATERIALIZED VIEW parcel_details AS
SELECT 
    p.id AS parcel_id,
    p.lot_plan,
    p.lot,
    p.plan_number,
    p.parcel_type,
    p.tenure,
    p.area_sqm,
    p.lga,
    p.locality,
    a.full_address,
    z.zone_code,
    z.zone_short,
    z.planning_scheme,
    pr.max_height_m,
    pr.max_storeys,
    pr.min_lot_size_sqm,
    pr.max_site_cover_pct,
    pr.front_setback_m,
    pr.side_setback_m,
    pr.rear_setback_m,
    p.geom
FROM parcels p
LEFT JOIN addresses a ON a.parcel_id = p.id
LEFT JOIN zones z ON ST_Intersects(p.geom, z.geom)
LEFT JOIN planning_rules pr ON pr.zone_code = z.zone_code AND pr.lga = p.lga;
```

---

## 6. API Endpoints (MVP)

### `GET /v1/lookup`
**Purpose:** Look up a property by address or Lot/Plan

```bash
# By address
GET /v1/lookup?address=15+Abbott+St+Camp+Hill+QLD+4152

# By Lot/Plan
GET /v1/lookup?lot=3&plan=RP12345
```

**Response:**
```json
{
  "parcel": {
    "lot_plan": "3/RP12345",
    "lot": "3",
    "plan": "RP12345",
    "type": "Base",
    "tenure": "Freehold",
    "area_sqm": 607,
    "lga": "Brisbane City",
    "locality": "Camp Hill",
    "address": "15 Abbott St, Camp Hill QLD 4152"
  },
  "zoning": {
    "zone_code": "Low density residential",
    "zone_short": "LDR",
    "planning_scheme": "Brisbane City Plan 2014"
  },
  "overlays": [
    { "type": "Flood", "name": "Flood overlay - Medium risk" },
    { "type": "Character", "name": "Traditional building character overlay" }
  ],
  "geometry": {
    "type": "Feature",
    "geometry": { "type": "Polygon", "coordinates": [...] }
  }
}
```

### `GET /v1/buildability`
**Purpose:** What can you build on this lot?

```bash
GET /v1/buildability?lot=3&plan=RP12345
```

**Response:**
```json
{
  "parcel": { "lot_plan": "3/RP12345", "area_sqm": 607 },
  "zoning": { "zone_code": "Low density residential" },
  "rules": {
    "max_height_m": 9.5,
    "max_storeys": 2,
    "min_lot_size_sqm": 400,
    "max_site_cover_pct": 50,
    "front_setback_m": 6,
    "side_setback_m": 1.5,
    "rear_setback_m": 6,
    "max_dwelling_density": "1 per 400sqm"
  },
  "buildable_envelope": {
    "max_footprint_sqm": 303.5,
    "max_gfa_sqm": 607,
    "max_dwellings": 1,
    "buildable_area_after_setbacks_sqm": 420
  },
  "accepted_uses": ["Dwelling house", "Home-based business"],
  "assessable_uses": ["Dual occupancy", "Secondary dwelling"],
  "key_constraints": [
    "Flood overlay - Medium risk: may require flood assessment",
    "Character overlay: design must respect traditional character"
  ],
  "ai_confidence": 0.92,
  "disclaimer": "Indicative only. Always verify with council."
}
```

### `GET /v1/report`
**Purpose:** Full property due diligence report (PDF)

```bash
GET /v1/report?address=15+Abbott+St+Camp+Hill&format=pdf
```

Returns a professional PDF with map, parcel data, zoning, overlays, planning rules, buildability summary.

### `GET /v1/search`
**Purpose:** Address autocomplete

```bash
GET /v1/search?q=15+Abbott+St+Camp
```

Returns matching addresses for type-ahead search.

---

## 7. Nightly Sync Pipeline

```python
# sync_pipeline.py — runs at 2am AEST via cron

"""
1. Fetch cadastral parcels from QLD ArcGIS REST
   - Layer 4: Cadastral parcels (all of QLD)
   - Uses pagination (maxRecordCount=5000)
   - Outputs: GeoJSON
   
2. Fetch addresses
   - Layer 0: Addresses
   - Link to parcels via spatial join
   
3. Fetch tenure
   - Layer 13: Tenure
   
4. Load to PostGIS
   - Upsert parcels (match on lot_plan)
   - Upsert addresses
   - Update tenure
   - Refresh materialized views
   
5. Log + alert
   - Count records synced
   - Flag any errors
   - Compare with previous sync (detect data anomalies)
"""

# ArcGIS REST query template
PARCELS_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query"
)

# Query params for pagination
params = {
    "where": "1=1",           # all records
    "outFields": "*",         # all fields
    "f": "geojson",          # GeoJSON format
    "resultOffset": 0,        # pagination start
    "resultRecordCount": 5000, # max per request
    "outSR": 4283             # GDA94
}
```

---

## 8. Phase Plan

### Phase 1: MVP (Tonight → Week 1)
**Goal:** Working API that returns parcel + address data for any QLD lot

- [ ] Set up PostgreSQL + PostGIS (local Docker or Railway)
- [ ] Write sync script for DCDB parcels (Layer 4)
- [ ] Write sync script for addresses (Layer 0)  
- [ ] Build FastAPI with `/lookup` and `/search` endpoints
- [ ] Test with Sunshine Coast addresses (familiar territory)
- [ ] Deploy to Railway/Fly.io

**Deliverable:** `GET /v1/lookup?address=X` returns parcel boundary + basic data

### Phase 2: Zoning (Week 2-3)
**Goal:** Add zoning data and "what zone is this lot in?"

- [ ] Source planning scheme spatial data (QPlan WFS or council-specific)
- [ ] Start with Sunshine Coast + Brisbane (2 biggest, Juliano knows them)
- [ ] Add zones table + spatial overlay queries
- [ ] `/lookup` now includes zoning info

### Phase 3: Planning Rules Engine (Week 3-4)
**Goal:** AI-parsed planning rules → buildability answers

- [ ] Download planning scheme PDFs for SCC + BCC
- [ ] Use Claude to extract zone → rules mapping (height, setbacks, FSR, uses)
- [ ] Build `planning_rules` table
- [ ] `/buildability` endpoint live
- [ ] `/report` endpoint (PDF generation)

### Phase 4: Overlays + Polish (Month 2)
**Goal:** Flood, heritage, bushfire overlays + professional UI

- [ ] Add overlay datasets (flood, bushfire, heritage, character)
- [ ] Build frontend map viewer (MapLibre GL)
- [ ] Add authentication + API keys
- [ ] Rate limiting + usage tracking
- [ ] Landing page + docs

### Phase 5: Monetise (Month 2-3)
**Goal:** Start charging

- [ ] Free tier: 50 lookups/month
- [ ] Pro: $49/mo (1,000 lookups)
- [ ] Enterprise: $199/mo (unlimited + PDF reports)
- [ ] Target: planners, developers, conveyancers, engineers

---

## 9. Tonight's Session — What to Build

### Setup (30 min)
1. Docker Compose: PostgreSQL + PostGIS + Redis
2. FastAPI project scaffold
3. `.env` with database config

### Core (2-3 hours)
1. **Sync script** — download DCDB parcels for Sunshine Coast LGA only (manageable size)
2. **Address sync** — download addresses for same area
3. **Lookup endpoint** — address → parcel → return GeoJSON
4. **Search endpoint** — type-ahead address search

### Stretch Goals
5. Query a specific lot boundary and return it as GeoJSON
6. Simple HTML map viewer (Leaflet) to visualize results
7. Deploy to Railway

---

## 10. Competitive Advantage

| Geoscape | Urbix |
|----------|-------|
| $50k+/year enterprise | $49/mo self-serve |
| Raw data, you interpret | **AI-interpreted buildability** |
| No planning rules | **"Can I build X here?" in plain English** |
| Slow procurement process | Instant API key signup |
| Generic (all industries) | **Built by engineers, for development** |

**Moat:** The AI planning rules engine. Anyone can serve cadastre data. Nobody is serving "what can I build here?" with AI-parsed planning rules at this price point.

---

## 11. Revenue Potential

- **QLD alone:** ~4,500 town planners + ~3,000 civil engineers + ~5,000 conveyancers + ~2,000 property developers = **14,500 potential users**
- At 2% conversion × $49/mo = **$14k/mo just from QLD**
- National (NSW, VIC, WA, SA, TAS, NT) = 5x market = **$70k/mo potential**
- Enterprise (councils, banks, insurers) = 10-50x per customer

This has real potential to be the biggest revenue driver in the portfolio.

---

## Files Created
- `/Users/janainamdeoliveira/clawd/urbix-api/PLAN.md` — this document

## References
- QLD Spatial Services: https://spatial-gis.information.qld.gov.au/arcgis/rest/services/PlanningCadastre
- DCDB Layer: MapServer/4 (Cadastral parcels)
- Addresses Layer: MapServer/0
- Land Use: FeatureServer/0
