-- Ground-truth labels per building, derived from the City's land use (primary), OPA (cross-check)
-- and L&I licences. Used only to score classifiers; never to build evidence (see decision 0007).
CREATE TABLE IF NOT EXISTS ground_truth (
    building_id           int PRIMARY KEY REFERENCES building (id) ON DELETE CASCADE,
    crosswalk_version     text NOT NULL,
    land_use_c1           int,
    land_use_c2           int,
    d1_class              text NOT NULL,   -- residential | commercial | mixed-use | industrial | civic-institutional | vacant | other
    opa_category          text,            -- majority OPA category of parcel points inside the footprint
    opa_class             text,            -- OPA category mapped to the same classes
    label_status          text NOT NULL,   -- agree | land_use_only | disputed
    split_footprint       boolean NOT NULL, -- footprint overlaps two land-use classes, each >= 25%
    food_serving_licenses int NOT NULL,    -- active "Food Preparing and Serving" licences within 15 m
    food_retail_licenses  int NOT NULL,    -- active "Food Establishment, Retail" licences within 15 m
    d3_food               boolean NOT NULL, -- food_serving_licenses > 0
    split                 text NOT NULL    -- train | dev | test, grouped by street so blocks never straddle splits
);
CREATE INDEX IF NOT EXISTS ground_truth_split_idx ON ground_truth (split, d1_class);

-- Rule and model baselines write here (Jev decisions get their own table later).
CREATE TABLE IF NOT EXISTS baseline_prediction (
    building_id   int  NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    baseline      text NOT NULL,   -- e.g. rules-v1
    d1_class      text NOT NULL,
    d2_type       text,
    d3_food       boolean NOT NULL,
    rule          text NOT NULL,   -- which rule fired, for error analysis
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (building_id, baseline)
);

-- Street-level train/dev/test assignment, made once and then frozen: rebuilding upstream tables must
-- never move a street between splits (that would leak the test set into development).
CREATE TABLE IF NOT EXISTS split_assignment (
    group_key   text PRIMARY KEY,   -- "<area slug>|<street name>" (or an edge id for unnamed streets)
    split       text NOT NULL,      -- train | dev | test
    assigned_at timestamptz NOT NULL DEFAULT now()
);
