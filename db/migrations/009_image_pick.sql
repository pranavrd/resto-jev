-- The Mapillary image chosen for each building (if any image faces its frontage). Metadata only.
CREATE TABLE IF NOT EXISTS image_pick (
    building_id int PRIMARY KEY REFERENCES building (id) ON DELETE CASCADE,
    image_id    text NOT NULL,
    dist_m      double precision NOT NULL,
    angle_deg   double precision NOT NULL,   -- between camera heading and the direction of the frontage
    score       double precision NOT NULL,   -- lower is better
    year        int,
    picked_at   timestamptz NOT NULL DEFAULT now()
);
