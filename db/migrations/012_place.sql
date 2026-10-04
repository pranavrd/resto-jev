-- A place is a business operating at a location: the unit the restaurant census counts and, later, the unit that gets
-- matched to Yelp. Buildings are containers; one building can hold several places.
CREATE TABLE IF NOT EXISTS place (
    id            serial PRIMARY KEY,
    area_id       int  NOT NULL REFERENCES area (id),
    building_id   int  REFERENCES building (id) ON DELETE SET NULL,
    name          text,
    kind          text NOT NULL,       -- restaurant | fast food | cafe | bar | ice cream | bakery or deli | other food | licensed food service
    geom          geometry(Point, 4326) NOT NULL,
    sources       text[] NOT NULL,     -- {osm}, {licence} or {osm,licence}
    osm_type      text,
    osm_id        bigint,
    licence_id    bigint,              -- business_license.cartodb_id
    licence_type  text,
    licence_name  text,
    address       text,
    match_score   double precision,
    match_basis   text,                -- name+building, address, building 1:1 (names differ), ...
    confidence    text NOT NULL,       -- high | medium | low
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS place_geom_idx ON place USING gist (geom);
CREATE INDEX IF NOT EXISTS place_building_idx ON place (building_id);
