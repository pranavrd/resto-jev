-- Street group of each building (the unit the train/dev/test split and grouped CV keep together).
ALTER TABLE ground_truth ADD COLUMN IF NOT EXISTS group_key text;

-- Probabilistic baselines store their class probabilities and top-class confidence, so calibration
-- can be compared across baselines and Jev.
ALTER TABLE baseline_prediction ADD COLUMN IF NOT EXISTS probs jsonb;
ALTER TABLE baseline_prediction ADD COLUMN IF NOT EXISTS confidence double precision;
