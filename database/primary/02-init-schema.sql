-- Schema definition for predictions table
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    username VARCHAR(100),
    model_name VARCHAR(100) NOT NULL DEFAULT 'iris_classifier',
    model_version VARCHAR(50) NOT NULL DEFAULT 'v1.0.0',
    features JSONB NOT NULL,
    prediction VARCHAR(100) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    probabilities JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predictions_user_id ON predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at);

