-- Mapillary's raw compass_angle comes from the device; computed_compass_angle comes from structure-from-motion
-- and is usually more accurate (median disagreement 7 degrees, a few outliers beyond 100).
ALTER TABLE mapillary_image ADD COLUMN IF NOT EXISTS computed_compass double precision;
