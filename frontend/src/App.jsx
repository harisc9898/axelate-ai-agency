import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "https://leadgen-ai-api.onrender.com";

const FORMAT_META = {
  reel:      { icon: "▶", label: "Reel" },
  carousel:  { icon: "▦", label: "Carousel" },
};

const STATUS_META = {
  draft:     { label: "Draft",     color: "var(--warn)" },
  approved:  { label: "Approved",  color: "var(--good)" },
  discarded: { label: "Discarded", color: "var(--muted)" },
  published: { label: "Published",color: "var(--accent2)" },
};

function useStyles() {
  return {
    page: { minHeight: "100vh", background: "var(--bg)", fontFamily: "'Inter', system-ui, sans-serif", color: "var(--text)" },
    header: { background: "var(--surface)", borderBottom: "1px solid var(--border)", padding: "0 24px" },
    headerInner: { maxWidth: 1040, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 },
    brandRow: { display: "flex", alignItems: "center", gap: 12 },
    logo: { width: 38, height: 38, borderRadius: 10, background: "linear-gradient(135deg, var(--accent), var(--accent2))", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 700, color: "#fff", fontFamily: "'Space Grotesk', sans-serif" },
    title: { fontWeight: 700, fontSize: 17, color: "var(--text)", fontFamily: "'Space Grotesk', sans-serif", letterSpacing: -0.3 },
    subtitle: { fontSize: 11.5, color: "var(--muted)", marginTop: 1 },
    statusPill: (running) => ({ display: "flex", alignItems: "center", gap: 7, padding: "6px 14px", borderRadius: 20, background: running ? "rgba(99,102,241,0.15)" : "rgba(34,197,94,0.12)", border: `1px solid ${running ? "var(--accent)" : "var(--good)"}`, fontSize: 12.5, fontWeight: 500, color: running ? "var(--accent)" : "var(--good)" }),
    dot: (running) => ({ width: 6, height: 6, borderRadius: "50%", background: running ? "var(--accent)" : "var(--good)", display: "inline-block" }),
    tabs: { background: "var(--surface)", borderBottom: "1px solid var(--border)" },
    tabsInner: { maxWidth: 1040, margin: "0 auto", display: "flex" },
    tabBtn: (active) => ({ padding: "13px 20px", background: "none", border: "none", borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent", color: active ? "var(--accent)" : "var(--muted)", fontWeight: 500, fontSize: 13.5, cursor: "pointer", fontFamily: "inherit" }),
    container: { maxWidth: 1040, margin: "0 auto", padding: "24px" },
    card: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 20 },
    statGrid: { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 },
    statCard: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px", textAlign: "center" },
    statNum: { fontSize: 24, fontWeight: 700, color: "var(--text)", fontFamily: "'Space Grotesk', sans-serif" },
    statLabel: { fontSize: 11.5, color: "var(--muted)", marginTop: 4 },
    btnPrimary: { padding: "10px 18px", background: "linear-gradient(135deg, var(--accent), var(--accent2))", border: "none", borderRadius: 9, color: "#fff", fontWeight: 600, fontSize: 13.5, cursor: "pointer", fontFamily: "inherit" },
    btnGhost: { padding: "9px 16px", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 9, color: "var(--text)", fontWeight: 500, fontSize: 13, cursor: "pointer", fontFamily: "inherit" },
    btnDanger: { padding: "9px 16px", background: "rgba(239,68,68,0.1)", border: "1px solid var(--bad)", borderRadius: 9, color: "var(--bad)", fontWeight: 500, fontSize: 13, cursor: "pointer", fontFamily: "inherit" },
    select: { padding: "9px 12px", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 9, color: "var(--text)", fontSize: 13, fontFamily: "inherit" },
    triggerBadge: { display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 10px", background: "rgba(99,102,241,0.12)", border: "1px solid var(--accent)", borderRadius: 6, fontFamily: "'Space Grotesk', monospace", fontSize: 12, fontWeight: 600, color: "var(--accent)" },
    textarea: { width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: 10, fontSize: 13, fontFamily: "inherit", resize: "vertical", minHeight: 70 },
  };
}

export default function App() {
  const s = useStyles();
  const [activeTab, setActiveTab] = useState("queue");
  const [status, setStatus] = useState(null);
  const [queue, setQueue] = useState([]);
  const [queueFilter, setQueueFilter] = useState("draft");
  const [pillars, setPillars] = useState([]);
  const [polling, setPolling] = useState(false);
  const [genFormat, setGenFormat] = useState("reel");
  const [genPillar, setGenPillar] = useState("");
  const [edits, setEdits] = useState({});

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/status`);
      const d = await r.json();
      setStatus(d);
      setPolling(!!d.running);
    } catch (e) {}
  }, []);

  const fetchQueue = useCallback(async (f) => {
    try {
      const r = await fetch(`${API_BASE}/queue?status=${f}`);
      const d = await r.json();
      setQueue(Array.isArray(d) ? d : []);
    } catch (e) {}
  }, []);

  const fetchPillars = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/pillars`);
      const d = await r.json();
      setPillars(d.pillars || []);
    } catch (e) {}
  }, []);

  useEffect(() => { fetchStatus(); fetchQueue(queueFilter); fetchPillars(); }, []);
  useEffect(() => { fetchQueue(queueFilter); }, [queueFilter]);

  useEffect(() => {
    if (!polling) return;
    const id = setInterval(() => { fetchStatus(); fetchQueue(queueFilter); }, 4000);
    return () => clearInterval(id);
  }, [polling, fetchStatus, fetchQueue, queueFilter]);

  const startGenerate = async (format, pillar) => {
    try {
      await fetch(`${API_BASE}/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format, pillar: pillar || null }),
      });
      setPolling(true);
      fetchStatus();
    } catch (e) { alert("Could not reach backend. Check it's deployed and VITE_API_URL is set."); }
  };

  const startDailyBatch = async () => {
    try {
      await fetch(`${API_BASE}/generate/daily-batch`, { method: "POST" });
      setPolling(true);
      fetchStatus();
    } catch (e) { alert("Could not reach backend."); }
  };

  const approvePost = async (id) => {
    await fetch(`${API_BASE}/posts/${id}/approve`, { method: "POST" });
    fetchQueue(queueFilter);
  };
  const discardPost = async (id) => {
    await fetch(`${API_BASE}/posts/${id}/discard`, { method: "POST" });
    fetchQueue(queueFilter);
  };
  const regeneratePost = async (id) => {
    await fetch(`${API_BASE}/posts/${id}/regenerate`, { method: "POST" });
    setPolling(true);
    fetchStatus();
  };
  const saveEdit = async (id) => {
    const body = edits[id];
    if (!body) return;
    await fetch(`${API_BASE}/posts/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    fetchQueue(queueFilter);
  };
  const setEditField = (id, field, value) => {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], [field]: value } }));
  };

  const isRunning = status?.running;
  const draftCount = queue.filter((p) => p.status === "draft").length;
  const approvedCount = queue.filter((p) => p.status === "approved").length;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <div style={s.headerInner}>
          <div style={s.brandRow}>
            <div style={s.logo}>L</div>
            <div>
              <div style={s.title}>LeadGen.ai</div>
              <div style={s.subtitle}>Instagram lead engine · Phase 1</div>
            </div>
          </div>
          <div style={s.statusPill(isRunning)}>
            <span style={s.dot(isRunning)}></span>
            {isRunning ? (status?.step || "Generating…") : "Ready"}
          </div>
        </div>
      </div>

      <div style={s.tabs}>
        <div style={s.tabsInner}>
          {["queue", "generate", "pillars", "stack"].map((t) => (
            <button key={t} onClick={() => setActiveTab(t)} style={s.tabBtn(activeTab === t)}>
              {t === "queue" ? "Review Queue" : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div style={s.container}>
        {/* ── STATS (always visible) ─────────────────────────────────── */}
        <div style={s.statGrid}>
          {[
            { num: draftCount, label: "Awaiting review" },
            { num: approvedCount, label: "Approved" },
            { num: "2+/day", label: "Target cadence" },
            { num: "$0", label: "Monthly cost" },
          ].map((st, i) => (
            <div key={i} style={s.statCard}>
              <div style={s.statNum}>{st.num}</div>
              <div style={s.statLabel}>{st.label}</div>
            </div>
          ))}
        </div>

        {/* ── REVIEW QUEUE TAB ───────────────────────────────────────── */}
        {activeTab === "queue" && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              {["draft", "approved", "discarded", "all"].map((f) => (
                <button key={f} onClick={() => setQueueFilter(f)}
                  style={{ ...s.btnGhost, background: queueFilter === f ? "rgba(99,102,241,0.12)" : "var(--bg)", borderColor: queueFilter === f ? "var(--accent)" : "var(--border)", color: queueFilter === f ? "var(--accent)" : "var(--text)" }}>
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>

            {queue.length === 0 && (
              <div style={{ ...s.card, textAlign: "center", color: "var(--muted)", padding: 40 }}>
                Nothing here yet. Head to <strong style={{ color: "var(--accent)" }}>Generate</strong> to create your first batch.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {queue.map((post) => {
                const fm = FORMAT_META[post.format] || FORMAT_META.reel;
                const stm = STATUS_META[post.status] || STATUS_META.draft;
                const e = edits[post.id] || {};
                return (
                  <div key={post.id} style={s.card}>
                    <div style={{ display: "flex", gap: 16 }}>
                      {/* Media preview */}
                      <div style={{ width: 180, flexShrink: 0 }}>
                        {post.format === "reel" && post.media_urls?.video && (
                          <video src={post.media_urls.video} controls style={{ width: "100%", borderRadius: 10, background: "#000" }} />
                        )}
                        {post.format === "carousel" && post.media_urls?.slides && (
                          <div style={{ display: "flex", gap: 4, overflowX: "auto" }}>
                            {post.media_urls.slides.map((url, i) => (
                              <img key={i} src={url} alt={`slide ${i + 1}`} style={{ width: 60, height: 75, objectFit: "cover", borderRadius: 6, flexShrink: 0 }} />
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Content */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 13 }}>{fm.icon} {fm.label}</span>
                          <span style={{ padding: "2px 9px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: "var(--bg)", color: "var(--muted)", border: "1px solid var(--border)" }}>{post.pillar}</span>
                          <span style={{ padding: "2px 9px", borderRadius: 6, fontSize: 11, fontWeight: 600, color: stm.color, background: "var(--bg)", border: `1px solid ${stm.color}` }}>{stm.label}</span>
                          {post.trigger_word && <span style={s.triggerBadge}>💬 "{post.trigger_word}"</span>}
                        </div>

                        <div style={{ fontWeight: 600, fontSize: 14.5, marginBottom: 6 }}>{post.hook}</div>

                        <textarea
                          style={s.textarea}
                          defaultValue={post.caption}
                          onChange={(ev) => setEditField(post.id, "caption", ev.target.value)}
                        />
                        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>{post.hashtags}</div>

                        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                          <button style={s.btnGhost} onClick={() => saveEdit(post.id)}>Save edits</button>
                          {post.status !== "approved" && (
                            <button style={s.btnPrimary} onClick={() => approvePost(post.id)}>Approve</button>
                          )}
                          <button style={s.btnGhost} onClick={() => regeneratePost(post.id)}>Regenerate</button>
                          {post.status !== "discarded" && (
                            <button style={s.btnDanger} onClick={() => discardPost(post.id)}>Discard</button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* ── GENERATE TAB ───────────────────────────────────────────── */}
        {activeTab === "generate" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={s.card}>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, fontFamily: "'Space Grotesk', sans-serif" }}>Today's batch</div>
              <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>Generates 1 Reel + 1 Carousel, rotating pillars automatically. Lands in the Review Queue as drafts.</div>
              <button style={s.btnPrimary} disabled={isRunning} onClick={startDailyBatch}>
                {isRunning ? "Generating…" : "Generate today's batch"}
              </button>
            </div>

            <div style={s.card}>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, fontFamily: "'Space Grotesk', sans-serif" }}>One-off generation</div>
              <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>Pick a format and optionally a specific pillar.</div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <select style={s.select} value={genFormat} onChange={(e) => setGenFormat(e.target.value)}>
                  <option value="reel">Reel</option>
                  <option value="carousel">Carousel</option>
                </select>
                <select style={s.select} value={genPillar} onChange={(e) => setGenPillar(e.target.value)}>
                  <option value="">Auto-rotate pillar</option>
                  {pillars.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
                <button style={s.btnPrimary} disabled={isRunning} onClick={() => startGenerate(genFormat, genPillar)}>
                  {isRunning ? "Generating…" : "Generate"}
                </button>
              </div>
            </div>

            {status && (status.running || status.error || status.step) && (
              <div style={s.card}>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 10 }}>Pipeline status</div>
                <div style={{ fontSize: 13, color: isRunning ? "var(--accent)" : "var(--muted)" }}>
                  {status.step_index ? `Step ${status.step_index}/${status.total_steps} — ` : ""}{status.step}
                </div>
                {status.error && (
                  <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(239,68,68,0.1)", borderRadius: 8, fontSize: 13, color: "var(--bad)" }}>
                    ❌ {status.error}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── PILLARS TAB ────────────────────────────────────────────── */}
        {activeTab === "pillars" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {pillars.map((p) => (
              <div key={p.id} style={s.card}>
                <div style={{ fontWeight: 600, fontSize: 14.5, marginBottom: 6, fontFamily: "'Space Grotesk', sans-serif" }}>{p.label}</div>
                <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.5 }}>{p.angle}</div>
              </div>
            ))}
            {pillars.length === 0 && <div style={{ color: "var(--muted)" }}>Loading pillars…</div>}
          </div>
        )}

        {/* ── STACK TAB ──────────────────────────────────────────────── */}
        {activeTab === "stack" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={s.card}>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, fontFamily: "'Space Grotesk', sans-serif" }}>Free tool stack</div>
              <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>Total cost: $0/month</div>
              {[
                { name: "Gemini 2.5 Flash / Groq / OpenRouter", desc: "Script, caption + carousel copy (cascade)", cost: "Free tier" },
                { name: "Edge TTS (Microsoft)", desc: "Reel voiceover", cost: "Free forever" },
                { name: "Cloudflare Workers AI (FLUX.1-schnell)", desc: "Reel scenes + carousel art", cost: "Free 10k neurons/day" },
                { name: "FFmpeg + Pillow", desc: "Video assembly, captions, carousel text", cost: "Free forever" },
                { name: "Supabase", desc: "Post + lead database, media storage", cost: "Free tier" },
                { name: "Render.com", desc: "Backend hosting", cost: "Free tier" },
                { name: "Vercel", desc: "Frontend hosting", cost: "Free forever" },
              ].map((t, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderBottom: i < 6 ? "1px solid var(--border)" : "none" }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{t.name}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.desc}</div>
                  </div>
                  <span style={{ padding: "3px 10px", background: "rgba(34,197,94,0.12)", color: "var(--good)", borderRadius: 6, fontSize: 12, fontWeight: 500, whiteSpace: "nowrap" }}>{t.cost}</span>
                </div>
              ))}
            </div>

            <div style={{ ...s.card, background: "rgba(99,102,241,0.08)", borderColor: "var(--accent)" }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Setup checklist</div>
              <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.7 }}>
                1. Set <code>VITE_API_URL</code> in Vercel to your Render backend URL.<br />
                2. Create a free Supabase project → run <code>supabase_schema.sql</code> → create a public Storage bucket named <code>media</code>.<br />
                3. Add all API keys as env vars on Render (Gemini/Groq/OpenRouter, Cloudflare, Supabase, agency handle + booking link).<br />
                4. Instagram publishing isn't wired up yet — this is Phase 1 (generation + review only).
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600;700&display=swap');
        :root {
          --bg: #0B0D17;
          --surface: #12162A;
          --border: #232840;
          --text: #F4F5FA;
          --muted: #8A8FA8;
          --accent: #6366F1;
          --accent2: #3B82F6;
          --good: #22C55E;
          --warn: #F59E0B;
          --bad: #EF4444;
        }
        * { box-sizing: border-box; }
        body { margin: 0; }
        code { background: var(--bg); border: 1px solid var(--border); padding: 1px 5px; border-radius: 4px; font-size: 12px; }
        select, textarea, button { outline: none; }
        button:hover { opacity: 0.92; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
      `}</style>
    </div>
  );
}
