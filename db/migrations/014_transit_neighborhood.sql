-- SEPTA stops with the service they get on one typical weekday, and City neighborhood polygons (decision 0017).
-- Stops are kept only near the survey areas. `service` maps "route|direction" to weekday stop-times.
CREATE TABLE IF NOT EXISTS transit_stop (
    feed          text NOT NULL,        -- bus (includes subway and trolley) | rail
    stop_id       text NOT NULL,
    name          text NOT NULL,
    geom          geometry(Point, 4326) NOT NULL,
    modes         text[] NOT NULL,      -- bus | subway | tram | rail
    service       jsonb NOT NULL,
    weekday_trips int NOT NULL,
    service_date  date NOT NULL,
    feed_version  text,
    PRIMARY KEY (feed, stop_id)
);
CREATE INDEX IF NOT EXISTS transit_stop_geom_idx ON transit_stop USING gist (geom);

CREATE TABLE IF NOT EXISTS neighborhood (
    id       serial PRIMARY KEY,
    name     text NOT NULL,
    listname text NOT NULL,
    geom     geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS neighborhood_geom_idx ON neighborhood USING gist (geom);

-- Context written onto each place by enrich.py. Distances are straight-line metres.
ALTER TABLE place ADD COLUMN IF NOT EXISTS neighborhood text;
ALTER TABLE place ADD COLUMN IF NOT EXISTS nearest_stop_name text;
ALTER TABLE place ADD COLUMN IF NOT EXISTS nearest_stop_m real;
ALTER TABLE place ADD COLUMN IF NOT EXISTS nearest_rail_name text;   -- subway, trolley or regional rail
ALTER TABLE place ADD COLUMN IF NOT EXISTS nearest_rail_m real;
ALTER TABLE place ADD COLUMN IF NOT EXISTS stops_400m int;
ALTER TABLE place ADD COLUMN IF NOT EXISTS routes_400m text[];
ALTER TABLE place ADD COLUMN IF NOT EXISTS modes_400m text[];
ALTER TABLE place ADD COLUMN IF NOT EXISTS weekday_trips_400m int;

-- Fuzzy name search for the /places endpoint.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS place_name_trgm_idx ON place USING gin (lower(coalesce(name, '')) gin_trgm_ops);
