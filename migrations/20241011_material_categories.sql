BEGIN;

CREATE TABLE IF NOT EXISTS material_categories (
    id              SERIAL PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    content_key     TEXT NOT NULL UNIQUE,
    parent_id       INT REFERENCES material_categories(id) ON DELETE CASCADE,
    requires_access BOOLEAN NOT NULL DEFAULT TRUE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INT NOT NULL DEFAULT 100,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_categories_parent
    ON material_categories(parent_id);

CREATE TABLE IF NOT EXISTS material_category_access (
    id          SERIAL PRIMARY KEY,
    category_id INT NOT NULL REFERENCES material_categories(id) ON DELETE CASCADE,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    granted_by  BIGINT,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    UNIQUE (category_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_material_category_access_user
    ON material_category_access(user_id);

CREATE INDEX IF NOT EXISTS idx_material_category_access_category
    ON material_category_access(category_id);

-- Seed default categories
INSERT INTO material_categories (slug, title, content_key, requires_access, sort_order)
VALUES
    ('podcasts', 'Подкасты', 'menu.materials.podcasts', TRUE, 10),
    ('practices', 'Практики', 'menu.materials.practices', TRUE, 20),
    ('challenges', 'Челленджи', 'menu.materials.challenges', TRUE, 30),
    ('archive', 'Архив недель', 'menu.materials.archive', TRUE, 40)
ON CONFLICT (slug) DO UPDATE
    SET title = EXCLUDED.title,
        content_key = EXCLUDED.content_key,
        requires_access = EXCLUDED.requires_access,
        sort_order = EXCLUDED.sort_order,
        updated_at = NOW();

INSERT INTO material_categories (slug, title, content_key, parent_id, requires_access, sort_order)
SELECT 'archive.week1', 'Неделя 1', 'menu.materials.archive.week1', id, TRUE, 41
FROM material_categories
WHERE slug = 'archive'
ON CONFLICT (slug) DO UPDATE
    SET title = EXCLUDED.title,
        content_key = EXCLUDED.content_key,
        parent_id = EXCLUDED.parent_id,
        requires_access = EXCLUDED.requires_access,
        sort_order = EXCLUDED.sort_order,
        updated_at = NOW();

COMMIT;
