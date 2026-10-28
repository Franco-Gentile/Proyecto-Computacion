-- ============================================================================
-- Esquema de Base de Datos PostgreSQL — Reproductor de Video Distribuido
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(32) NOT NULL UNIQUE CHECK (length(btrim(username)) >= 3),
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    original_filename TEXT NOT NULL CHECK (length(btrim(original_filename)) > 0),
    path TEXT NOT NULL UNIQUE CHECK (length(btrim(path)) > 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    duration_s DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (duration_s >= 0.0),
    width INTEGER NOT NULL DEFAULT 0 CHECK (width >= 0),
    height INTEGER NOT NULL DEFAULT 0 CHECK (height >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'uploading'
        CHECK (status IN ('uploading', 'processing', 'ready', 'error')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_owner_id ON videos(owner_id);
