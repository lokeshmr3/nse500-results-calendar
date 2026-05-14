-- Run once in Supabase SQL Editor → New Query

CREATE TABLE IF NOT EXISTS calendar_entries (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol      TEXT    NOT NULL,
    name        TEXT,
    sector      TEXT,
    date        TEXT,
    description TEXT,
    attachment  TEXT,
    market_cap  FLOAT8  DEFAULT 0,
    market_cap_cr FLOAT8 DEFAULT 0,
    quarter     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calendar_meta (
    id          INT  PRIMARY KEY DEFAULT 1,
    quarter     TEXT,
    updated_at  TEXT,
    from_date   TEXT,
    to_date     TEXT
);

-- Personal project — disable RLS so the anon/publishable key can read & write
ALTER TABLE calendar_entries DISABLE ROW LEVEL SECURITY;
ALTER TABLE calendar_meta    DISABLE ROW LEVEL SECURITY;
