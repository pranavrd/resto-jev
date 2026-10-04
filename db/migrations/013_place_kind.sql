-- Kind of a licensed place, inferred by Jev from its name and licence (OSM supplies kinds only for mapped places).
ALTER TABLE place ADD COLUMN IF NOT EXISTS kind_jev text;
ALTER TABLE place ADD COLUMN IF NOT EXISTS kind_jev_conf double precision;
ALTER TABLE place ADD COLUMN IF NOT EXISTS kind_source text;   -- osm | jev
