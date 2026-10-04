-- The panorama to cut a view from for each building, and the compass bearing to point the view at. Metadata only.
CREATE TABLE IF NOT EXISTS pano_pick (
    building_id int PRIMARY KEY REFERENCES building (id) ON DELETE CASCADE,
    image_id    text NOT NULL,
    dist_m      double precision NOT NULL,
    bearing_deg double precision NOT NULL,
    heading_deg double precision NOT NULL,   -- compass heading of the panorama's centre column (the raw compass_angle)
    year        int,
    picked_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE pano_pick ADD COLUMN IF NOT EXISTS heading_deg double precision;
