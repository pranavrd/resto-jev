-- Raw ingest tables. Derived tables (building, place, decision, ...) come in later weeks.
-- All geometries are EPSG:4326; use ST_Transform for metric work.

CREATE TABLE IF NOT EXISTS area (
    id       serial PRIMARY KEY,
    slug     text UNIQUE NOT NULL,
    name     text NOT NULL,
    profile  text NOT NULL,
    geom     geometry(Polygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS osm_building (
    osm_type  text   NOT NULL,
    osm_id    bigint NOT NULL,
    area_id   int    NOT NULL REFERENCES area (id),
    geom      geometry(Geometry, 4326) NOT NULL,
    tags      jsonb  NOT NULL DEFAULT '{}',
    pulled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (osm_type, osm_id, area_id)
);
CREATE INDEX IF NOT EXISTS osm_building_geom_idx ON osm_building USING gist (geom);

CREATE TABLE IF NOT EXISTS osm_poi (
    osm_type  text   NOT NULL,
    osm_id    bigint NOT NULL,
    area_id   int    NOT NULL REFERENCES area (id),
    geom      geometry(Geometry, 4326) NOT NULL,
    tags      jsonb  NOT NULL DEFAULT '{}',
    pulled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (osm_type, osm_id, area_id)
);
CREATE INDEX IF NOT EXISTS osm_poi_geom_idx ON osm_poi USING gist (geom);

CREATE TABLE IF NOT EXISTS osm_street (
    area_id    int    NOT NULL REFERENCES area (id),
    u          bigint NOT NULL,
    v          bigint NOT NULL,
    k          int    NOT NULL,
    osm_way_id text,
    highway    text,
    name       text,
    length_m   double precision,
    geom       geometry(LineString, 4326) NOT NULL,
    pulled_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (area_id, u, v, k)
);
CREATE INDEX IF NOT EXISTS osm_street_geom_idx ON osm_street USING gist (geom);

-- City of Philadelphia: property assessments (point per tax account)
CREATE TABLE IF NOT EXISTS opa_parcel (
    parcel_number             text PRIMARY KEY,
    category_code             text,
    category_code_description text,
    building_code_description text,
    zoning                    text,
    number_stories            double precision,
    total_area                double precision,
    total_livable_area        double precision,
    year_built                text,
    location                  text,
    geom                      geometry(Point, 4326),
    pulled_at                 timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS opa_parcel_geom_idx ON opa_parcel USING gist (geom);

-- City of Philadelphia: PCPC land use polygons
CREATE TABLE IF NOT EXISTS land_use (
    objectid   bigint PRIMARY KEY,
    c_dig1     int,
    c_dig2     int,
    c_dig3     int,
    c_dig1desc text,
    c_dig2desc text,
    c_dig3desc text,
    year       int,
    vacbldg    int,
    geom       geometry(Geometry, 4326) NOT NULL,
    pulled_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS land_use_geom_idx ON land_use USING gist (geom);

-- City of Philadelphia: L&I business licenses (owner contact fields intentionally not stored)
CREATE TABLE IF NOT EXISTS business_license (
    cartodb_id          bigint PRIMARY KEY,
    licensenum          text,
    licensetype         text,
    licensestatus       text,
    address             text,
    business_name       text,
    legalname           text,
    initialissuedate    timestamptz,
    mostrecentissuedate timestamptz,
    expirationdate      timestamptz,
    inactivedate        timestamptz,
    parcel_id_num       text,
    opa_account_num     text,
    geom                geometry(Point, 4326),
    pulled_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS business_license_geom_idx ON business_license USING gist (geom);
CREATE INDEX IF NOT EXISTS business_license_type_idx ON business_license (licensetype, licensestatus);

-- Mapillary image metadata only (IDs, capture date, heading, position). Images are not stored.
CREATE TABLE IF NOT EXISTS mapillary_image (
    id            text PRIMARY KEY,
    area_id       int  NOT NULL REFERENCES area (id),
    captured_at   timestamptz,
    compass_angle double precision,
    is_pano       boolean,
    geom          geometry(Point, 4326) NOT NULL,
    pulled_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mapillary_image_geom_idx ON mapillary_image USING gist (geom);
