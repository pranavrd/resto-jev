-- Which building each business POI belongs to (also the start of the restaurant "place" table).
CREATE TABLE IF NOT EXISTS poi_link (
    area_id     int    NOT NULL REFERENCES area (id),
    osm_type    text   NOT NULL,
    osm_id      bigint NOT NULL,
    building_id int    NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    match       text   NOT NULL,           -- contained | nearby
    dist_m      double precision NOT NULL,
    PRIMARY KEY (area_id, osm_type, osm_id)
);
CREATE INDEX IF NOT EXISTS poi_link_building_idx ON poi_link (building_id);

-- Evidence per building and tier. Tier 0 = OSM + geometry + walk context (no imagery).
CREATE TABLE IF NOT EXISTS evidence (
    building_id int  NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    tier        int  NOT NULL,
    version     text NOT NULL,
    payload     jsonb NOT NULL,
    text        text NOT NULL,             -- exactly what Jev is shown
    image_id    text,                      -- tier 1+: Mapillary image used
    caption     text,                      -- tier 1+: vision-model caption
    built_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (building_id, tier)
);
