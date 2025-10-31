BEGIN;

CREATE TABLE IF NOT EXISTS material_assets (
    id SERIAL PRIMARY KEY,
    category_id INT NOT NULL REFERENCES material_categories(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('text','audio','video')),
    title TEXT,
    body TEXT,
    file_id TEXT,
    sort_order INT NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_assets_category
    ON material_assets(category_id);

COMMIT;
