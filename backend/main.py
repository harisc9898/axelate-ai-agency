"""
LeadGen.ai — Backend v1.0 (Phase 1)
══════════════════════════════════════════════════════════════════
Instagram content engine for an AI-automation agency.
Generates faceless Reels + Carousels designed to drive inbound
leads (comment-keyword CTAs), holds them in a Review Queue for
approval/edit, and stores everything in Supabase (free, persistent —
Render's disk is wiped on every restart, so nothing lead-related
lives there).

STACK (all free tier):
  Text     — Gemini 2.5 Flash → Groq Llama 3.3 → OpenRouter (cascade)
  Voice    — Edge-TTS (Microsoft neural voices, free forever)
  Images   — Cloudflare Workers AI FLUX.1-schnell (10k neurons/day free)
  Video    — FFmpeg Ken Burns + ASS captions
  Carousel — Pillow typography only (black/red brand palette, no photos —
             matches the proven bold-text-carousel format used by top
             coaching/agency accounts)
  Storage  — Supabase (Postgres + Storage, free tier, persistent)
  Hosting  — Render (backend) + Vercel (frontend), both free

PHASE 1 SCOPE:
  ✅ Content Engine (pillar rotation, trigger-word assignment)
  ✅ Media Engine (Reels + Carousels)
  ✅ Review Queue (draft → edit → approve/discard/regenerate)
  ❌ Instagram publishing (Phase 2 — needs Meta app + IG business acct)
  ❌ Comment-to-DM automation / webhook (Phase 2)

ENV VARS NEEDED:
  GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY   (text — at least one)
  CF_ACCOUNT_ID, CF_API_TOKEN                         (images)
  SUPABASE_URL, SUPABASE_SERVICE_KEY                  (persistence)
  AGENCY_HANDLE                                       (e.g. "@youragency")
  AGENCY_BOOKING_LINK                                 (e.g. Calendly URL)
══════════════════════════════════════════════════════════════════
"""

import os, json, time, random, asyncio, subprocess, re, shutil, base64
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import requests

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── ENV VARS ────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY        = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
CF_ACCOUNT_ID       = os.environ.get("CF_ACCOUNT_ID", "")
CF_API_TOKEN        = os.environ.get("CF_API_TOKEN", "")
SUPABASE_URL        = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY        = os.environ.get("SUPABASE_SERVICE_KEY", "")
AGENCY_HANDLE       = os.environ.get("AGENCY_HANDLE", "@youragency")
AGENCY_BOOKING_LINK = os.environ.get("AGENCY_BOOKING_LINK", "link in bio")

# ── APP ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="LeadGen.ai API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

WORK_DIR = Path("/tmp/leadgen")
WORK_DIR.mkdir(exist_ok=True)

pipeline_status: dict = {
    "running": False, "step": "", "step_index": 0, "total_steps": 1,
    "format": None, "error": None, "llm_used": None,
    "image_source": None, "last_result": None,
}

VID_W, VID_H, CLIP_FPS = 720, 1280, 25
CAR_W, CAR_H = 1080, 1350          # Instagram carousel 4:5

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FONT_SERIF_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

# Carousel brand palette — typography-only design (no photos), alternating
# background per slide, inspired by top-performing coach/agency carousels.
CAROUSEL_PALETTE = {
    "black": {"bg": (10, 9, 11), "text": (247, 243, 235), "accent": (196, 30, 58)},
    "red":   {"bg": (139, 20, 30), "text": (247, 243, 235), "accent": (10, 9, 11)},
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONTENT STRATEGY — pillars, business context, services
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS_CONTEXT = """You are writing Instagram content for an AI automation agency.
The agency sells: AI voice receptionists, AI calling agents (inbound/outbound),
AI chatbots (website + Instagram/WhatsApp DMs), lead automation and instant
follow-up systems, and lead reactivation campaigns that revive cold/old leads.
The audience is small-to-medium business owners (contractors, clinics, real
estate, salons, local service businesses, agencies) losing revenue because of
slow or manual response to leads. Tone: confident, direct, no fluff — like a
founder who actually builds this stuff, not a corporate marketing account."""

SERVICES = [
    "an AI voice receptionist that answers every call 24/7",
    "AI calling agents that follow up on leads within seconds",
    "an AI chatbot that replies to website and Instagram DMs instantly",
    "a lead automation system that never lets a lead go cold",
    "a lead reactivation campaign that revives old, dead leads",
    "the exact AI content system generating this very post",
]

PILLARS = {
    "pain_agitation": {
        "label": "Pain Agitation",
        "angle": ("Open with the specific, costly consequence of NOT having "
                  "automation — missed calls at night, slow lead response, "
                  "no-shows, hours lost to manual DMs. Make the business "
                  "owner feel the cost in the first line."),
    },
    "myth_busting": {
        "label": "Myth Busting",
        "angle": ("Take a common objection or myth about AI (sounds robotic, "
                  "too expensive, will replace my team, too complicated) and "
                  "dismantle it directly with a confident correction."),
    },
    "proof_authority": {
        "label": "Proof & Authority",
        "angle": ("Explain exactly how a specific automation works under the "
                  "hood, like a mini behind-the-scenes build. Position the "
                  "creator as the person who actually builds this stuff."),
    },
    "roi_math": {
        "label": "ROI Math",
        "angle": ("Do simple, concrete math showing the dollar cost of "
                  "inaction vs the dollar return of automation (e.g. missed "
                  "leads per month × average deal value). Numbers-driven, blunt."),
    },
    "objection_handling": {
        "label": "Objection Handling",
        "angle": ("Address a specific hesitation business owners have before "
                  "buying AI services (privacy, job loss, reliability, cost) "
                  "with a short, respectful, confident rebuttal."),
    },
    "case_study": {
        "label": "Case Study / Win",
        "angle": ("Tell a short before-and-after story of a business that "
                  "implemented one of these automations — what changed "
                  "operationally and financially."),
    },
}

BIZ_STYLE = ("clean modern flat illustration, soft gradient background, tech "
             "startup aesthetic, indigo and electric-blue accent colors, "
             "minimalist geometric shapes, subtle glow, no text, no watermark, "
             "no logo, no readable UI text, no distorted faces")


class GenerateRequest(BaseModel):
    format: str                       # "reel" | "carousel"
    pillar: Optional[str] = None


class EditRequest(BaseModel):
    hook: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    trigger_word: Optional[str] = None
    cta_dm_message: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SUPABASE — persistence layer (Postgres + Storage via REST)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _sb_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _sb_headers(extra: dict = None) -> dict:
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def sb_insert(table: str, data: dict) -> dict:
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}",
                       headers=_sb_headers({"Prefer": "return=representation"}),
                       json=data, timeout=20)
    if r.status_code not in (200, 201):
        raise Exception(f"Supabase insert failed: {r.status_code} {r.text[:200]}")
    rows = r.json()
    return rows[0] if rows else {}


def sb_select(table: str, params: dict = None) -> list:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}",
                      headers=_sb_headers(), params=params or {}, timeout=20)
    if r.status_code != 200:
        raise Exception(f"Supabase select failed: {r.status_code} {r.text[:200]}")
    return r.json()


def sb_update(table: str, row_id: str, data: dict) -> dict:
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}",
                        headers=_sb_headers({"Prefer": "return=representation"}),
                        params={"id": f"eq.{row_id}"}, json=data, timeout=20)
    if r.status_code not in (200, 201):
        raise Exception(f"Supabase update failed: {r.status_code} {r.text[:200]}")
    rows = r.json()
    return rows[0] if rows else {}


def sb_upload_file(local_path: str, storage_path: str, content_type: str) -> str:
    data = Path(local_path).read_bytes()
    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/media/{storage_path}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": content_type, "x-upsert": "true"},
        data=data, timeout=60)
    if r.status_code not in (200, 201):
        raise Exception(f"Supabase storage upload failed: {r.status_code} {r.text[:200]}")
    return f"{SUPABASE_URL}/storage/v1/object/public/media/{storage_path}"


def get_next_pillar(exclude: Optional[str] = None) -> str:
    keys = list(PILLARS.keys())
    if exclude and exclude in keys and len(keys) > 1:
        keys = [k for k in keys if k != exclude]
    # Try to avoid repeating the very last pillar used, if we can see history
    if _sb_ready():
        try:
            last = sb_select("posts", {"select": "pillar", "order": "created_at.desc", "limit": "1"})
            if last and last[0].get("pillar") in keys and len(keys) > 1:
                keys = [k for k in keys if k != last[0]["pillar"]]
        except Exception:
            pass
    return random.choice(keys)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM CASCADE (Gemini → Groq → OpenRouter — all free-tier)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def call_gemini(prompt: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}")
        resp = requests.post(url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2500}},
            timeout=60)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Gemini {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"Gemini failed: {e}")
    return None


def call_groq(prompt: str) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.85, "max_tokens": 2500}, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        print(f"Groq {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"Groq failed: {e}")
    return None


def call_openrouter(prompt: str) -> Optional[str]:
    headers = {"Content-Type": "application/json", "HTTP-Referer": "https://leadgen-ai.onrender.com"}
    if OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
    for model in ["meta-llama/llama-3.3-70b-instruct:free",
                  "google/gemma-3-27b-it:free",
                  "mistralai/mistral-7b-instruct:free"]:
        try:
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.85, "max_tokens": 2500}, timeout=90)
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                if text and len(text) > 100:
                    return text
        except Exception as e:
            print(f"OpenRouter {model}: {e}")
    return None


def _clean_json(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip()).rstrip("`").strip()
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        raw = m.group(0)
    raw = raw.encode('utf-8', errors='ignore').decode('utf-8')
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', raw)
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    for text in [raw, raw.replace('\n', ' '), re.sub(r'\s+', ' ', raw)]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def call_llm_cascade(prompt: str) -> tuple:
    raw = call_gemini(prompt)
    if raw:
        return raw, "Gemini 2.5 Flash"
    raw = call_groq(prompt)
    if raw:
        return raw, "Groq Llama 3.3 70B"
    raw = call_openrouter(prompt)
    if raw:
        return raw, "OpenRouter"
    raise Exception("All LLM providers failed — check GEMINI_API_KEY/GROQ_API_KEY/OPENROUTER_API_KEY")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROMPT BUILDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_reel_prompt(pillar_key: str) -> str:
    p = PILLARS[pillar_key]
    service = random.choice(SERVICES)
    return f"""{BUSINESS_CONTEXT}

CONTENT PILLAR: {p['label']}
ANGLE: {p['angle']}
FEATURED SERVICE (weave in naturally, don't force it): {service}

Write a script for a 25-40 second FACELESS Instagram Reel (voiceover only, no
on-camera talent).

RULES:
1. HOOK: first 1-2 sentences must stop the scroll — a sharp claim, a number,
   or a pointed question. Never "Hey guys" or "In this video".
2. Short, punchy, spoken-English sentences. No jargon.
3. Build to a clear insight/payoff, then pivot to a soft pitch for the
   featured service.
4. End with a CTA telling the viewer to comment ONE specific keyword to get
   more info via DM.
5. LENGTH: 70-110 word spoken script.
6. Also write an Instagram caption: 3-5 short lines with line breaks (not a
   wall of text) that restates the hook/insight and repeats the exact CTA.
7. trigger_word: ONE short uppercase word or 2-word phrase, topic-relevant
   (e.g. CALLS, LEADS, REVIVE, BOT, AUTOMATE). Must exactly match the CTA
   used in both script and caption.
8. cta_dm_message: the auto-DM sent when someone comments the trigger word —
   thank them, one-line value prop, end with "Book a free call: {{LINK}}".
9. 4-6 short visual scene prompts for AI image generation depicting modern
   business/tech scenarios (office, phone, dashboard, chat bubbles, night
   storefront). Environment/screen-focused — do not describe detailed faces.
   Each scene: subject + setting + lighting + camera angle.
10. hashtags: 15-20 tags mixing broad business/entrepreneur tags with niche
    AI-automation tags, space-separated, include #.

Return ONLY valid JSON, no markdown, no backticks, nothing outside the JSON:
{{
  "hook": "...",
  "script": "70-110 word spoken script",
  "caption": "line 1\\nline 2\\nline 3",
  "hashtags": "#tag1 #tag2 #tag3",
  "trigger_word": "CALLS",
  "cta_dm_message": "...",
  "scenes": ["scene 1", "scene 2", "scene 3", "scene 4", "scene 5"],
  "pillar": "{pillar_key}"
}}"""


HOOK_PATTERNS = [
    "A confident 'how real [role] actually do X' framing that implies most people are doing it wrong",
    "A short, blunt cause-and-effect: 'I stopped/didn't do [action] for [specific timeframe]. [Surprising result]. Here's why.'",
    "A direct callout of a common bad habit: 'Stop saying/doing [common thing]. Say/do [better thing] instead.'",
    "A numbered-reasons hook: '[N] reasons your [thing] isn't working.'",
    "A humbling personal-stakes opener: 'I made a lot of mistakes before [milestone].'",
    "An uncomfortable-truth confession using a specific number: 'I had [specific number] and made $[specific number]. Here's the uncomfortable truth.'",
    "A myth-correction: 'Your [thing] is doing [surface-level metric]. That's not the real problem. It's [real problem].'",
]


def build_carousel_prompt(pillar_key: str) -> str:
    p = PILLARS[pillar_key]
    service = random.choice(SERVICES)
    hook_pattern = random.choice(HOOK_PATTERNS)
    return f"""{BUSINESS_CONTEXT}

CONTENT PILLAR: {p['label']}
ANGLE: {p['angle']}
FEATURED SERVICE (weave in naturally, don't force it): {service}

Write a 5-7 slide Instagram carousel in the style of top-performing
business/coaching carousel accounts: bold typography only, ONE idea per
slide, no fluff, every slide creates a reason to swipe to the next.

HOOK STYLE FOR SLIDE 1 (use this exact pattern, written fresh — do not reuse
these instructions as literal text, write an original line following the
pattern): {hook_pattern}

RULES:
1. Slide 1 (cover): the hook headline (max 12 words, punchy, no period at
   the end) plus an optional short subheading/teaser (max 8 words, e.g.
   "Here's why" / "Here's the breakdown" / "Swipe for the full story").
   Every word must earn its place — cut anything generic.
2. Slides 2 to second-last: one sharp idea per slide. Short heading (max 6
   words) + short body (max 16 words). Be specific and slightly
   contrarian/counter-intuitive where possible — generic advice does not
   get saved. Each slide should make the reader want to know what's next.
3. Second-to-last slide should land the core insight/payoff clearly enough
   that someone screenshotting just that slide would still get value
   (drives saves).
4. Final slide: a direct CTA telling the reader to comment ONE specific
   keyword to get more info via DM. Make it feel like a natural next step,
   not a hard sell.
5. trigger_word: ONE short uppercase word or 2-word phrase, topic-relevant.
   Must exactly match the CTA on the final slide.
6. caption: 3-5 short lines (line breaks, not a wall of text). Re-hook in
   line 1 (someone should be able to read just the first line in the feed
   before "more" and still be intrigued). End with an explicit prompt to
   save the post for later AND the comment-keyword CTA.
7. hashtags: 15-20 tags, space-separated, include #. Mix: 4-5 broad
   business/entrepreneur tags (large reach), 6-8 niche AI-automation/agency
   tags (targeted reach), 3-4 small/specific long-tail tags (low competition,
   higher chance of ranking). Avoid ultra-generic single-word tags like
   #love or #instagood — they dilute relevance.
8. cta_dm_message: auto-DM sent when someone comments the trigger word —
   thank them, one-line value prop, end with "Book a free call: {{LINK}}".

Return ONLY valid JSON, no markdown, no backticks, nothing outside the JSON:
{{
  "hook": "Cover headline",
  "subheading": "Cover subheading or teaser",
  "slides": [
    {{"heading": "Point 1", "body": "short specific point"}},
    {{"heading": "Point 2", "body": "short specific point"}},
    {{"heading": "Point 3", "body": "short specific point"}},
    {{"heading": "Point 4", "body": "short specific point"}},
    {{"heading": "CALL TO ACTION", "body": "Comment TRIGGERWORD for..."}}
  ],
  "caption": "line 1\\nline 2\\nline 3",
  "hashtags": "#tag1 #tag2 #tag3",
  "trigger_word": "LEADS",
  "cta_dm_message": "...",
  "pillar": "{pillar_key}"
}}"""


def generate_reel_content(pillar: str) -> dict:
    raw, llm = call_llm_cascade(build_reel_prompt(pillar))
    data = _clean_json(raw)
    if not data:
        raise Exception(f"JSON parse failed. Raw[:300]: {raw[:300]}")
    data["llm_used"] = llm
    data.setdefault("pillar", pillar)
    return data


def generate_carousel_content(pillar: str) -> dict:
    raw, llm = call_llm_cascade(build_carousel_prompt(pillar))
    data = _clean_json(raw)
    if not data:
        raise Exception(f"JSON parse failed. Raw[:300]: {raw[:300]}")
    data["llm_used"] = llm
    data.setdefault("pillar", pillar)
    return data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VOICE (Edge-TTS primary, gTTS fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDGE_PROFILES = {
    "confident": {"voice": "en-US-GuyNeural",    "rate": "+2%", "pitch": "-4Hz"},
    "warm":      {"voice": "en-US-AriaNeural",   "rate": "+0%", "pitch": "-2Hz"},
    "sharp":     {"voice": "en-GB-RyanNeural",   "rate": "+4%", "pitch": "-2Hz"},
}


async def _edge_tts_async(text, voice, rate, pitch, audio_out, timings_out):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    sub = edge_tts.SubMaker()
    events = []
    with open(audio_out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                sub.feed(chunk)
                s = chunk["offset"] / 10_000_000
                d = chunk["duration"] / 10_000_000
                events.append({"word": chunk["text"], "start": round(s, 3), "end": round(s + d, 3)})
    with open(timings_out, "w") as f:
        json.dump(events, f)
    return events


def _fallback_timings(text: str, duration: float) -> list:
    words = text.split()
    if not words:
        return []
    tpw = duration / len(words)
    return [{"word": w, "start": round(i * tpw, 3), "end": round((i + 1) * tpw, 3)} for i, w in enumerate(words)]


def get_duration(path: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1", path],
                            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 30.0


def generate_voice(content: str, style: str, audio_path: str, timings_path: str) -> list:
    profile = EDGE_PROFILES.get(style, EDGE_PROFILES["confident"])
    try:
        events = asyncio.run(_edge_tts_async(content, profile["voice"], profile["rate"], profile["pitch"], audio_path, timings_path))
        if events:
            return events
    except Exception as e:
        print(f"  edge-tts failed: {e}")
    try:
        from gtts import gTTS
        gTTS(text=content, lang="en", tld="com", slow=False).save(audio_path)
    except Exception as e:
        raise Exception(f"All TTS failed: {e}")
    dur = get_duration(audio_path)
    wt = _fallback_timings(content, dur)
    with open(timings_path, "w") as f:
        json.dump(wt, f)
    return wt


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASS CAPTIONS — bottom-center, business/authority style (not mid-screen meme style)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _ass_time(s: float) -> str:
    cs = int((s % 1) * 100)
    sec = int(s) % 60
    mn = int(s) // 60 % 60
    hr = int(s) // 3600
    return f"{hr}:{mn:02d}:{sec:02d}.{cs:02d}"


def generate_ass_subtitles(word_timings: list, ass_path: str):
    if not word_timings:
        Path(ass_path).write_text("", encoding="utf-8")
        return
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VID_W}
PlayResY: {VID_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,DejaVu Sans,64,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,6,0,2,40,40,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cards = []
    i = 0
    while i < len(word_timings):
        group = word_timings[i:i + 3]
        i += 3
        start = group[0]["start"]
        end = max(group[-1]["end"], start + 0.35)
        text = " ".join(w["word"] for w in group)
        text = text.replace("{", "").replace("}", "").replace("\\", "")
        cards.append((_ass_time(start), _ass_time(end), text))
    lines = [f"Dialogue: 0,{s},{e},Main,,0,0,0,,{t}" for s, e, t in cards]
    Path(ass_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMAGE GENERATION — Cloudflare FLUX.1-schnell primary, cinematic fallback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _verify_image(path: str, min_size: int = 8_000) -> bool:
    p = Path(path)
    if not p.exists() or p.stat().st_size < min_size:
        return False
    header = p.read_bytes()[:4]
    return header[:3] == b'\xff\xd8\xff' or header[:4] == b'\x89PNG'


def cf_generate_image(prompt: str, output_path: str, width: int = 768, height: int = 1024) -> bool:
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return False
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    payload = {"prompt": prompt[:500], "num_steps": 8, "width": width, "height": height}
    try:
        resp = requests.post(url,
            headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
            json=payload, timeout=28)
        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if ct.startswith("image/"):
                Path(output_path).write_bytes(resp.content)
                return _verify_image(output_path)
            data = resp.json()
            b64 = (data.get("result", {}).get("image") or
                   data.get("result", {}).get("images", [{}])[0].get("image", ""))
            if b64:
                Path(output_path).write_bytes(base64.b64decode(b64))
                return _verify_image(output_path)
        else:
            print(f"CF: HTTP {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"CF error: {e}")
    return False


_BIZ_PALETTE = {"r": "0/0 0.3/0.15 0.7/0.3 1/0.42", "g": "0/0 0.3/0.12 0.7/0.28 1/0.4",
                 "b": "0/0 0.3/0.4 0.7/0.75 1/0.95", "base": "0x140F35"}


def generate_cinematic_fallback(output_path: str, width: int, height: int, label: str = "") -> bool:
    pal = _BIZ_PALETTE
    safe_label = label[:35].replace("'", "").replace(":", "").replace(",", "").replace('"', "")
    vf = (f"noise=alls=20:allf=t+u,curves=r='{pal['r']}':g='{pal['g']}':b='{pal['b']}',"
          f"vignette=PI/2.2,drawtext=text='{safe_label}':fontsize=22:fontcolor=white@0.12:"
          f"borderw=1:bordercolor=black@0.08:x=(w-text_w)/2:y=h*0.9:font=sans,format=yuvj420p")
    cmds = [
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"gradients=size={width}x{height}:x0=0:y0=0:x1={width}:y1={height}:c0={pal['base']}:c1=0x000000:duration=1",
         "-vf", vf, "-frames:v", "1", "-update", "1", output_path],
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={pal['base']}:size={width}x{height}:duration=1",
         "-vf", "noise=alls=18:allf=t+u,vignette=PI/2,format=yuvj420p", "-frames:v", "1", "-update", "1", output_path],
    ]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=12)
            if r.returncode == 0 and _verify_image(output_path, min_size=3_000):
                return True
        except Exception as e:
            print(f"Fallback error: {e}")
    return False


def generate_image(prompt: str, output_path: str, width: int, height: int, label: str = "") -> Optional[str]:
    if CF_ACCOUNT_ID and CF_API_TOKEN:
        if cf_generate_image(prompt, output_path, width, height):
            pipeline_status["image_source"] = "Cloudflare FLUX"
            return "cloudflare"
    if generate_cinematic_fallback(output_path, width, height, label):
        pipeline_status["image_source"] = "CinematicFallback"
        return "fallback"
    return None


def _biz_image_prompt(scene: str) -> str:
    return f"{scene}, {BIZ_STYLE}"


# ── Ken Burns (reel scenes) ──────────────────────────────────────────────────
_KB_W, _KB_H = int(VID_W * 1.45), int(VID_H * 1.45)


def _ken_burns_filter(duration: float, style: int) -> str:
    d = max(int(duration * CLIP_FPS), 2)
    s = style % 4
    if s == 0:
        return (f"scale={_KB_W}:{_KB_H},zoompan=z='min(zoom+0.0015,1.3)'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={VID_W}x{VID_H}:fps={CLIP_FPS}")
    elif s == 1:
        return (f"scale={_KB_W}:{_KB_H},zoompan=z='if(eq(on,1),1.3,max(zoom-0.0015,1.0))'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={VID_W}x{VID_H}:fps={CLIP_FPS}")
    elif s == 2:
        return (f"scale={_KB_W}:{_KB_H},zoompan=z='1.15':x='({_KB_W}-{VID_W}/1.15)*on/{d}'"
                f":y='({_KB_H}/2)-({VID_H}/1.15/2)':d={d}:s={VID_W}x{VID_H}:fps={CLIP_FPS}")
    else:
        return (f"scale={_KB_W}:{_KB_H},zoompan=z='1.15':x='({_KB_W}-{VID_W}/1.15)*(1-on/{d})'"
                f":y='({_KB_H}/2)-({VID_H}/1.15/2)':d={d}:s={VID_W}x{VID_H}:fps={CLIP_FPS}")


def build_scene_clip(scene: str, duration: float, output_path: str, kb_style: int) -> bool:
    img_path = output_path.replace(".mp4", ".jpg")
    prompt = _biz_image_prompt(scene)
    source = generate_image(prompt, img_path, 768, 1024, label=scene[:35])
    if not source or not _verify_image(img_path):
        return False
    kb_filter = _ken_burns_filter(duration, kb_style)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img_path, "-vf", f"{kb_filter},format=yuv420p",
           "-t", str(duration), "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
           "-r", str(CLIP_FPS), "-pix_fmt", "yuv420p", "-threads", "1", "-an", output_path]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        cmd2 = ["ffmpeg", "-y", "-loop", "1", "-i", img_path,
                "-vf", f"scale={VID_W}:{VID_H}:force_original_aspect_ratio=decrease,pad={VID_W}:{VID_H}:(ow-iw)/2:(oh-ih)/2:color=0x140F35,format=yuv420p",
                "-t", str(duration), "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-threads", "1", "-an", output_path]
        result = subprocess.run(cmd2, capture_output=True, timeout=180)
    Path(img_path).unlink(missing_ok=True)
    return result.returncode == 0 and Path(output_path).exists()


# ── Music ─────────────────────────────────────────────────────────────────
def generate_music(music_path: str) -> bool:
    style = "upbeat corporate tech ambient minimal ~ ~"
    try:
        r = requests.get(f"https://audio.pollinations.ai/{requests.utils.quote(style)}", timeout=35)
        if r.status_code == 200 and len(r.content) > 1000:
            Path(music_path).write_bytes(r.content)
            return True
    except Exception as e:
        print(f"Music failed: {e}")
    try:
        r = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                             "-t", "60", "-c:a", "aac", "-b:a", "128k", music_path],
                            capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


# ── Assembly ──────────────────────────────────────────────────────────────
def assemble_video(clips: list, voice_p: str, music_p: Optional[str], ass_p: str, output_p: str):
    ts = str(int(time.time()))
    txt = str(WORK_DIR / f"concat_{ts}.txt")
    with open(txt, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    concat_out = str(WORK_DIR / f"concat_{ts}.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", txt, "-c", "copy", concat_out],
                        capture_output=True, timeout=120)
    if r.returncode != 0:
        raise Exception(f"Concat failed: {r.stderr[-300:].decode(errors='ignore')}")
    voice_dur = min(get_duration(voice_p) + 0.5, 45.0)
    has_subs = ass_p and Path(ass_p).exists() and Path(ass_p).stat().st_size > 50
    use_music = music_p and Path(music_p).exists()
    vf = f"ass='{ass_p}'" if has_subs else "null"
    if use_music:
        afilt = ("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,volume=2.0[voice];"
                  "[2:a]volume=0.08,aloop=loop=-1:size=2e+09[music];"
                  "[voice][music]amix=inputs=2:duration=first[afinal]")
        cmd = ["ffmpeg", "-y", "-i", concat_out, "-i", voice_p, "-i", music_p, "-t", str(voice_dur),
               "-vf", vf, "-filter_complex", afilt, "-map", "0:v", "-map", "[afinal]",
               "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_p]
    else:
        cmd = ["ffmpeg", "-y", "-i", concat_out, "-i", voice_p, "-t", str(voice_dur), "-vf", vf,
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
               "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_p]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode != 0:
        raise Exception(f"Assembly failed: {r.stderr[-400:].decode(errors='ignore')}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAROUSEL COMPOSITING (Pillow) — pure typography, no photos
# Alternating black/red slides, bold serif headline, centered composition —
# matches the format proven to perform on info/coaching accounts (one idea
# per slide, cliffhanger into the next, save-worthy final insight slide).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _wrap_text(draw, text, font, max_width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def compose_carousel_slide(heading: str, body: str, idx: int, total: int, out_path: str,
                            is_cover: bool = False, is_cta: bool = False, subheading: str = ""):
    from PIL import Image, ImageDraw, ImageFont

    if is_cover or is_cta:
        palette = CAROUSEL_PALETTE["black"]
    else:
        palette = CAROUSEL_PALETTE["red"] if idx % 2 == 1 else CAROUSEL_PALETTE["black"]

    img = Image.new("RGB", (CAR_W, CAR_H), palette["bg"])
    draw = ImageDraw.Draw(img)

    heading_font = ImageFont.truetype(FONT_SERIF_BOLD, 78 if is_cover else 62)
    sub_font = ImageFont.truetype(FONT_SERIF_BOLD, 34)
    body_font = ImageFont.truetype(FONT_REG, 34)
    small_font = ImageFont.truetype(FONT_REG, 26)

    max_w = CAR_W - 160
    h_lines = _wrap_text(draw, heading, heading_font, max_w)
    b_lines = _wrap_text(draw, body, body_font, max_w) if body else []

    line_h = heading_font.size + 12
    block_h = len(h_lines) * line_h
    if b_lines:
        block_h += 24 + len(b_lines) * (body_font.size + 10)
    if is_cover and subheading:
        block_h += 20 + sub_font.size

    y = (CAR_H - block_h) / 2
    for line in h_lines:
        draw.text((80, y), line, font=heading_font, fill=palette["text"])
        y += line_h
    if is_cover and subheading:
        y += 20
        draw.text((80, y), subheading, font=sub_font, fill=palette["accent"])
        y += sub_font.size
    if b_lines:
        y += 24
        for line in b_lines:
            draw.text((80, y), line, font=body_font, fill=palette["text"])
            y += body_font.size + 10

    if not is_cover:
        draw.rectangle([80, 60, 130, 66], fill=palette["accent"])

    if idx < total - 1:
        draw.text((CAR_W - 150, 55), "swipe →", font=small_font, fill=palette["accent"])

    draw.text((80, 55), f"{idx + 1}/{total}", font=small_font, fill=palette["text"])
    handle_w = draw.textlength(AGENCY_HANDLE, font=small_font)
    draw.text((CAR_W - handle_w - 80, CAR_H - 70), AGENCY_HANDLE, font=small_font, fill=palette["text"])

    img.convert("RGB").save(out_path, quality=92)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERATION PIPELINES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_generate_reel(pillar: Optional[str], post_id: Optional[str] = None):
    pillar = pillar or get_next_pillar()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = WORK_DIR / f"reel_{ts}"
    session.mkdir(exist_ok=True)
    try:
        pipeline_status.update(step="Writing script + caption...", step_index=1, total_steps=6, format="reel", error=None)
        data = generate_reel_content(pillar)

        pipeline_status.update(step="Synthesizing voiceover...", step_index=2)
        voice_p, timings_p = str(session / "voice.mp3"), str(session / "timings.json")
        style = random.choice(list(EDGE_PROFILES.keys()))
        word_timings = generate_voice(data["script"], style, voice_p, timings_p)
        audio_dur = get_duration(voice_p)

        ass_p = str(session / "subs.ass")
        generate_ass_subtitles(word_timings, ass_p)

        pipeline_status.update(step="Generating scene visuals...", step_index=3)
        scenes = data.get("scenes", [])[:6]
        scene_dur = min(audio_dur / max(len(scenes), 1), 10.0)
        clips = []
        for i, scene in enumerate(scenes):
            out = str(session / f"scene_{i}.mp4")
            if build_scene_clip(scene, scene_dur, out, kb_style=i):
                clips.append(out)
        if not clips:
            raise Exception("All scenes failed — check CF_ACCOUNT_ID/CF_API_TOKEN")

        pipeline_status.update(step="Adding background music...", step_index=4)
        music_p = str(session / "music.mp3")
        if not generate_music(music_p):
            music_p = None

        pipeline_status.update(step="Assembling final video...", step_index=5)
        final_p = str(session / "final.mp4")
        assemble_video(clips, voice_p, music_p, ass_p, final_p)

        pipeline_status.update(step="Saving to review queue...", step_index=6)
        video_url = final_p
        if _sb_ready():
            video_url = sb_upload_file(final_p, f"reels/{ts}.mp4", "video/mp4")

        row = {
            "format": "reel", "pillar": pillar, "status": "draft",
            "hook": data.get("hook", ""), "caption": data.get("caption", ""),
            "hashtags": data.get("hashtags", ""), "trigger_word": data.get("trigger_word", ""),
            "cta_dm_message": data.get("cta_dm_message", "").replace("{LINK}", AGENCY_BOOKING_LINK),
            "media_urls": {"video": video_url}, "raw_content": data, "llm_used": data.get("llm_used", ""),
        }
        result = sb_insert("posts", row) if (_sb_ready() and not post_id) else \
                 (sb_update("posts", post_id, row) if _sb_ready() else row)

        pipeline_status.update(step="Done! 🎉", step_index=6, last_result=result)
    except Exception as e:
        pipeline_status["error"] = str(e)
        print(f"❌ Reel pipeline error: {e}")
        import traceback; traceback.print_exc()
    finally:
        pipeline_status["running"] = False
        shutil.rmtree(str(session), ignore_errors=True)


def run_generate_carousel(pillar: Optional[str], post_id: Optional[str] = None):
    pillar = pillar or get_next_pillar()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = WORK_DIR / f"car_{ts}"
    session.mkdir(exist_ok=True)
    try:
        pipeline_status.update(step="Writing carousel copy...", step_index=1, total_steps=3, format="carousel", error=None)
        data = generate_carousel_content(pillar)
        slides = data.get("slides", [])[:7]

        pipeline_status.update(step="Designing slides...", step_index=2)
        slide_defs = [{"heading": data.get("hook", ""), "body": "", "is_cover": True,
                       "subheading": data.get("subheading", "")}]
        for s in slides:
            slide_defs.append({"heading": s.get("heading", ""), "body": s.get("body", ""), "is_cover": False})
        if len(slide_defs) > 1:
            slide_defs[-1]["is_cta"] = True

        total = len(slide_defs)
        slide_urls = []
        for i, sd in enumerate(slide_defs):
            out_path = str(session / f"slide_{i}.jpg")
            compose_carousel_slide(
                sd.get("heading", ""), sd.get("body", ""), i, total, out_path,
                is_cover=sd.get("is_cover", False), is_cta=sd.get("is_cta", False),
                subheading=sd.get("subheading", ""),
            )
            slide_urls.append(out_path)

        pipeline_status.update(step="Saving to review queue...", step_index=3)
        final_urls = slide_urls
        if _sb_ready():
            final_urls = [sb_upload_file(p, f"carousels/{ts}/slide_{i}.jpg", "image/jpeg") for i, p in enumerate(slide_urls)]

        row = {
            "format": "carousel", "pillar": pillar, "status": "draft",
            "hook": data.get("hook", ""), "caption": data.get("caption", ""),
            "hashtags": data.get("hashtags", ""), "trigger_word": data.get("trigger_word", ""),
            "cta_dm_message": data.get("cta_dm_message", "").replace("{LINK}", AGENCY_BOOKING_LINK),
            "media_urls": {"slides": final_urls}, "raw_content": data, "llm_used": data.get("llm_used", ""),
        }
        result = sb_insert("posts", row) if (_sb_ready() and not post_id) else \
                 (sb_update("posts", post_id, row) if _sb_ready() else row)

        pipeline_status.update(step="Done! 🎉", step_index=4, last_result=result)
    except Exception as e:
        pipeline_status["error"] = str(e)
        print(f"❌ Carousel pipeline error: {e}")
        import traceback; traceback.print_exc()
    finally:
        pipeline_status["running"] = False
        shutil.rmtree(str(session), ignore_errors=True)


def run_daily_batch():
    pipeline_status["running"] = True
    p1 = get_next_pillar()
    run_generate_reel(p1)
    p2 = get_next_pillar(exclude=p1)
    pipeline_status["running"] = True
    run_generate_carousel(p2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/")
def root():
    return {"status": "ok", "service": "LeadGen.ai API v1.0", "supabase_connected": _sb_ready()}


@app.get("/health")
def health():
    keys = {
        "gemini": bool(GEMINI_API_KEY), "groq": bool(GROQ_API_KEY), "openrouter": bool(OPENROUTER_API_KEY),
        "cloudflare": bool(CF_ACCOUNT_ID and CF_API_TOKEN), "supabase": _sb_ready(),
    }
    return {"status": "healthy", "version": "1.0", "keys": keys, "timestamp": datetime.now().isoformat()}


@app.get("/pillars")
def get_pillars():
    return {"pillars": [{"id": k, **v} for k, v in PILLARS.items()]}


@app.post("/generate")
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    if pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    if req.format not in ("reel", "carousel"):
        raise HTTPException(status_code=400, detail="format must be 'reel' or 'carousel'")
    pipeline_status["running"] = True
    if req.format == "reel":
        background_tasks.add_task(run_generate_reel, req.pillar)
    else:
        background_tasks.add_task(run_generate_carousel, req.pillar)
    return {"status": "started", "format": req.format, "pillar": req.pillar or "auto"}


@app.post("/generate/daily-batch")
async def generate_daily_batch(background_tasks: BackgroundTasks):
    if pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    background_tasks.add_task(run_daily_batch)
    return {"status": "started", "batch": ["reel", "carousel"]}


@app.get("/status")
def get_status():
    return pipeline_status


@app.get("/queue")
def get_queue(status: Optional[str] = None):
    if not _sb_ready():
        return []
    params = {"order": "created_at.desc", "limit": "100"}
    if status and status != "all":
        params["status"] = f"eq.{status}"
    return sb_select("posts", params)


@app.patch("/posts/{post_id}")
def edit_post(post_id: str, req: EditRequest):
    if not _sb_ready():
        raise HTTPException(status_code=400, detail="Supabase not configured")
    data = {k: v for k, v in req.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    return sb_update("posts", post_id, data)


@app.post("/posts/{post_id}/approve")
def approve_post(post_id: str):
    if not _sb_ready():
        raise HTTPException(status_code=400, detail="Supabase not configured")
    return sb_update("posts", post_id, {"status": "approved"})


@app.post("/posts/{post_id}/discard")
def discard_post(post_id: str):
    if not _sb_ready():
        raise HTTPException(status_code=400, detail="Supabase not configured")
    return sb_update("posts", post_id, {"status": "discarded"})


@app.post("/posts/{post_id}/regenerate")
async def regenerate_post(post_id: str, background_tasks: BackgroundTasks):
    if not _sb_ready():
        raise HTTPException(status_code=400, detail="Supabase not configured")
    if pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    rows = sb_select("posts", {"id": f"eq.{post_id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Post not found")
    post = rows[0]
    pipeline_status["running"] = True
    if post["format"] == "reel":
        background_tasks.add_task(run_generate_reel, post["pillar"], post_id)
    else:
        background_tasks.add_task(run_generate_carousel, post["pillar"], post_id)
    return {"status": "regenerating", "post_id": post_id}
