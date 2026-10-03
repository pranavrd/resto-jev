-- Street graph nodes (needed to orient edge geometry and to place jumps between components)
CREATE TABLE IF NOT EXISTS osm_node (
    area_id int    NOT NULL REFERENCES area (id),
    id      bigint NOT NULL,
    geom    geometry(Point, 4326) NOT NULL,
    PRIMARY KEY (area_id, id)
);

-- One row per planned walk. Only the latest run per area is kept.
CREATE TABLE IF NOT EXISTS walk_run (
    id               serial PRIMARY KEY,
    area_id          int NOT NULL REFERENCES area (id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    params           jsonb NOT NULL,
    n_components     int,
    n_street_edges   int,
    street_km        double precision,
    walked_km        double precision,
    repeat_km        double precision,
    overhead_pct     double precision,
    naive_walked_km  double precision,  -- same graph eulerized with networkx's hop-count heuristic
    n_jumps          int,
    jump_km          double precision
);

-- The ordered street-segment sequence. Each segment is walked in the stored direction (u -> v).
CREATE TABLE IF NOT EXISTS walk_step (
    run_id    int    NOT NULL REFERENCES walk_run (id) ON DELETE CASCADE,
    area_id   int    NOT NULL REFERENCES area (id),
    seq       int    NOT NULL,
    component int    NOT NULL,
    u         bigint NOT NULL,
    v         bigint NOT NULL,
    edge_u    bigint NOT NULL,  -- key of the underlying osm_street row (direction may be reversed)
    edge_v    bigint NOT NULL,
    edge_k    int    NOT NULL,
    is_repeat boolean NOT NULL, -- true when this pass re-walks a segment already walked (or to be walked)
    is_jump   boolean NOT NULL, -- true on the first step of a component reached by a teleport
    length_m  double precision NOT NULL,
    geom      geometry(LineString, 4326) NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS walk_step_area_idx ON walk_step (area_id, seq);
