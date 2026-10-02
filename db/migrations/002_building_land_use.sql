-- Ground-truth land use per OSM building.
-- land_use contains a few huge background polygons (e.g. a ~19 km2 class-5 "Transportation" polygon
-- from 2025 that covers whole neighbourhoods) underneath the real parcel polygons, so a plain
-- point-in-polygon join is ambiguous. Take the smallest containing polygon.
CREATE OR REPLACE VIEW building_land_use AS
SELECT DISTINCT ON (b.osm_type, b.osm_id, b.area_id)
       b.osm_type, b.osm_id, b.area_id,
       lu.objectid AS land_use_objectid, lu.c_dig1, lu.c_dig2, lu.c_dig3, lu.year AS land_use_year,
       ST_Area(ST_Transform(lu.geom, 32618)) AS land_use_m2
FROM osm_building b
JOIN land_use lu ON ST_Intersects(lu.geom, ST_PointOnSurface(b.geom))
ORDER BY b.osm_type, b.osm_id, b.area_id, ST_Area(lu.geom);
