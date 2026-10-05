-- Full-text search over Yelp review text for the TableMap retrieval layer (decision 0023). PRIVATE: indexes Yelp Data.
-- The query must use the same expression, to_tsvector('english', text), for this index to apply.
CREATE INDEX IF NOT EXISTS yelp_review_fts_idx ON yelp_review USING gin (to_tsvector('english', text));
