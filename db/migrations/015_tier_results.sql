-- Outputs of the escalation tiers (decision 0018). One row per building and tier; re-running a tier replaces its row.
CREATE TABLE IF NOT EXISTS tier1_result (
    building_id   int PRIMARY KEY REFERENCES building (id) ON DELETE CASCADE,
    source        text NOT NULL,        -- pano-tight-v4 | photo-lower55-v3
    image_id      text,
    caption       text,
    street_level  text,
    own_sign      text,
    d1            jsonb,                -- Jev D1 probabilities given the caption
    d3_yes        double precision,
    d5_yes        double precision,
    vlm_seconds   double precision,
    jev_ms        int,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tier2_result (
    building_id   int PRIMARY KEY REFERENCES building (id) ON DELETE CASCADE,
    model         text NOT NULL,
    answer        text,                 -- D1 class, or null when the reply named none
    raw           text,
    seconds       double precision,
    created_at    timestamptz NOT NULL DEFAULT now()
);
