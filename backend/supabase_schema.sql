-- Run this once in Supabase → SQL Editor (free project at supabase.com)

create extension if not exists "pgcrypto";

create table if not exists posts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  format text not null,              -- 'reel' | 'carousel'
  pillar text not null,
  status text not null default 'draft', -- draft | approved | published | discarded
  hook text,
  caption text,
  hashtags text,
  trigger_word text,
  cta_dm_message text,
  media_urls jsonb,                  -- {"video": url} or {"slides": [url, ...]}
  raw_content jsonb,                 -- full LLM output, for debugging/regeneration
  llm_used text
);

create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  post_id uuid references posts(id),
  ig_username text,
  comment_text text,
  trigger_word text,
  dm_sent boolean default false
);

-- Enable Row Level Security but allow the service key full access
-- (the backend uses the service key, which bypasses RLS by default —
-- this is just future-proofing if you ever add a client-side reader)
alter table posts enable row level security;
alter table leads enable row level security;

-- ── Storage bucket ───────────────────────────────────────────────────────
-- Also required (do this in the Supabase dashboard, not SQL):
--   1. Go to Storage → Create a new bucket named "media"
--   2. Set it to PUBLIC (so the dashboard can display images/video directly)
--   3. That's it — the backend uploads reels/carousels into this bucket
