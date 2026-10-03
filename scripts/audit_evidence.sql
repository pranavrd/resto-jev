-- Audit of tier-0 evidence signal against ground truth. REPORTING ONLY: the bundles never read these tables.
-- Run: docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scripts/audit_evidence.sql

\echo '== 1. share of buildings carrying any use signal, by ground-truth class (land use)'
WITH sig AS (
  SELECT b.id, b.area_id,
    CASE WHEN lu.c_dig2 = 23 THEN 'mixed res/comm'
         WHEN lu.c_dig2 IN (21, 22) THEN 'commercial'
         WHEN lu.c_dig1 = 1 THEN 'residential'
         ELSE 'other' END AS truth,
    jsonb_array_length(e.payload->'pois') > 0 AS has_poi,
    (e.payload->'osm') ? 'use_tags' AS has_use_tag,
    (e.payload->'osm') ? 'name' AS has_name
  FROM building b JOIN evidence e ON e.building_id = b.id AND e.tier = 0
  LEFT JOIN building_land_use lu ON lu.osm_type = b.osm_type AND lu.osm_id = b.osm_id AND lu.area_id = b.area_id)
SELECT a.slug, truth, count(*) n,
  round(100.0 * count(*) FILTER (WHERE has_poi) / count(*)) AS pct_poi,
  round(100.0 * count(*) FILTER (WHERE has_use_tag) / count(*)) AS pct_use_tag,
  round(100.0 * count(*) FILTER (WHERE has_poi OR has_use_tag OR has_name) / count(*)) AS pct_any_signal
FROM sig JOIN area a ON a.id = sig.area_id GROUP BY 1, 2 ORDER BY 1, 3 DESC;

\echo '== 2. active food licences: is the licensed site's building carrying food evidence?'
WITH lic AS (
  SELECT l.cartodb_id, a.id AS area_id, l.geom FROM business_license l JOIN area a ON ST_Intersects(l.geom, a.geom)
  WHERE l.licensestatus = 'Active' AND l.licensetype LIKE 'Food Preparing%'),
matched AS (
  SELECT lic.cartodb_id, lic.area_id, b.id AS building_id,
    ST_Distance(ST_Transform(lic.geom, 32618), ST_Transform(b.geom, 32618)) AS d
  FROM lic CROSS JOIN LATERAL (
    SELECT id, geom FROM building WHERE area_id = lic.area_id ORDER BY geom <-> lic.geom LIMIT 1) b),
food AS (
  SELECT m.cartodb_id, m.area_id, m.d, e.payload,
    (EXISTS (SELECT 1 FROM jsonb_array_elements(e.payload->'pois') p
             WHERE p->'tags'->>'amenity' IN ('restaurant','cafe','fast_food','bar','pub','ice_cream','food_court','biergarten')
                OR p->'tags'->>'shop' IN ('bakery','deli','coffee','pastry','confectionery','butcher','greengrocer','convenience','supermarket'))
     OR (e.payload->'osm'->'use_tags'->>'amenity') IN ('restaurant','cafe','fast_food','bar','pub','ice_cream')) AS has_food_evidence
  FROM matched m JOIN evidence e ON e.building_id = m.building_id AND e.tier = 0 WHERE m.d <= 15)
SELECT a.slug, count(*) licences_in_a_building, count(*) FILTER (WHERE has_food_evidence) with_food_evidence,
  round(100.0 * count(*) FILTER (WHERE has_food_evidence) / count(*)) AS pct
FROM food JOIN area a ON a.id = food.area_id GROUP BY 1 ORDER BY 1;

\echo '== 3. bundles with NO use signal at all, split by truth'
WITH sig AS (
  SELECT b.area_id,
    CASE WHEN lu.c_dig2 = 23 THEN 'mixed res/comm' WHEN lu.c_dig2 IN (21, 22) THEN 'commercial'
         WHEN lu.c_dig1 = 1 THEN 'residential' ELSE 'other' END AS truth,
    NOT (jsonb_array_length(e.payload->'pois') > 0 OR (e.payload->'osm') ? 'use_tags' OR (e.payload->'osm') ? 'name') AS silent
  FROM building b JOIN evidence e ON e.building_id = b.id AND e.tier = 0
  LEFT JOIN building_land_use lu ON lu.osm_type = b.osm_type AND lu.osm_id = b.osm_id AND lu.area_id = b.area_id)
SELECT a.slug, count(*) FILTER (WHERE silent) silent_buildings,
  count(*) FILTER (WHERE silent AND truth IN ('commercial','mixed res/comm')) silent_but_commercial_or_mixed,
  count(*) FILTER (WHERE silent AND truth = 'residential') silent_residential
FROM sig JOIN area a ON a.id = sig.area_id GROUP BY 1 ORDER BY 1;
