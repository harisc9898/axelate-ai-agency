[README.md](https://github.com/user-attachments/files/29746662/README.md)
# LeadGen.ai — Phase 1

Instagram content engine for your AI-automation agency. Generates faceless
Reels and Carousels designed to drive comments → DMs → booked calls, and
holds everything in a Review Queue so nothing posts without your approval.

**Phase 1 scope:** content generation + review queue only. Instagram
publishing and comment-to-DM automation are Phase 2 (once your Meta/IG
setup is ready).

## 1. Create a free Supabase project

1. supabase.com → New project (free tier)
2. SQL Editor → paste and run `backend/supabase_schema.sql`
3. Storage → Create bucket → name it exactly `media` → set **Public**
4. Settings → API → copy your **Project URL** and **service_role key**
   (not the anon key — the backend needs the service role key)

## 2. Deploy the backend (Render)

1. Push the `backend/` folder to a GitHub repo
2. Render.com → New → Web Service → connect the repo → it will read `render.yaml`
3. Add environment variables (Render dashboard → Environment):
   - `GEMINI_API_KEY` — free at aistudio.google.com
   - `GROQ_API_KEY` — free at console.groq.com (fallback if Gemini rate-limits)
   - `OPENROUTER_API_KEY` — optional, second fallback
   - `CF_ACCOUNT_ID` / `CF_API_TOKEN` — free at cloudflare.com (Workers AI)
   - `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — from step 1
   - `AGENCY_HANDLE` — e.g. `@youragency`
   - `AGENCY_BOOKING_LINK` — your Calendly/booking URL
4. Deploy. Check `https://your-app.onrender.com/health` once live.

## 3. Deploy the frontend (Vercel)

1. Push the `frontend/` folder to a GitHub repo (or same repo, separate root)
2. Vercel.com → New Project → import the repo → framework auto-detects Vite
3. Add env var `VITE_API_URL` = your Render backend URL
4. Deploy.

## 4. Using it

- **Generate tab** → "Generate today's batch" creates 1 Reel + 1 Carousel as drafts
- **Review Queue tab** → preview, edit the caption inline, then Approve /
  Regenerate / Discard
- "Approved" doesn't post anywhere yet in Phase 1 — it just marks the post
  ready. Actual Instagram publishing gets wired in once your Meta Developer
  App + Instagram Business account are set up (see the agency setup
  checklist from our conversation).

## What's next (Phase 2)

- Instagram Graph API publishing (the Approve button actually posts)
- Webhook receiver for comment-to-DM automation on the assigned trigger words
- Leads Inbox tab reading from the `leads` table
