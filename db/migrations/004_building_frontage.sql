-- One row per surveyed building: which street segment it fronts, on which side, and where along it.
CREATE TABLE IF NOT EXISTS building (
    id              serial PRIMARY KEY,
    area_id         int    NOT NULL REFERENCES area (id),
    osm_type        text   NOT NULL,
    osm_id          bigint NOT NULL,
    geom            geometry(Geometry, 4326) NOT NULL,
    frontage_pt     geometry(Point, 4326) NOT NULL,
    edge_u          bigint NOT NULL,   -- the osm_street segment fronted (stored direction u -> v)
    edge_v          bigint NOT NULL,
    edge_k          int    NOT NULL,
    side            smallint NOT NULL, -- +1 left of the stored direction, -1 right
    dist_m          double precision NOT NULL,
    along_m         double precision NOT NULL,  -- from u, scaled to the segment's stored length
    assign_method   text   NOT NULL,   -- address | nearest | nearest_nonservice | nearest_far
    n_candidates    int    NOT NULL,
    margin_m        double precision,  -- gap to the nearest candidate on a different non-service street; small = corner
    nearest_same    boolean NOT NULL,  -- plain nearest-segment would have chosen the same street
    area_m2         double precision,
    levels          int,
    UNIQUE (area_id, osm_type, osm_id)
);
CREATE INDEX IF NOT EXISTS building_geom_idx ON building USING gist (geom);
CREATE INDEX IF NOT EXISTS building_edge_idx ON building (area_id, edge_u, edge_v, edge_k);

-- The walker's encounters, in order. Replaced whenever the walk or the frontages change.
CREATE TABLE IF NOT EXISTS walk_event (
    run_id      int    NOT NULL REFERENCES walk_run (id) ON DELETE CASCADE,
    event_seq   int    NOT NULL,
    area_id     int    NOT NULL REFERENCES area (id),
    step_seq    int    NOT NULL,
    building_id int    NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    side_walk   smallint NOT NULL,         -- +1 left, -1 right relative to the direction walked
    along_m     double precision NOT NULL, -- distance along the segment in the direction walked
    walked_m    double precision NOT NULL, -- distance walked since the start of the area walk
    sim_seconds double precision NOT NULL, -- simulated clock at 1.4 m/s
    PRIMARY KEY (run_id, event_seq),
    UNIQUE (run_id, building_id)
);
CREATE INDEX IF NOT EXISTS walk_event_building_idx ON walk_event (building_id);
