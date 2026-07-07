import React, { useState, useCallback } from "react";

const BRAND = {
  negro: "#202020",
  burdeos: "#963058",
  rosa: "#E96A73",
  azulOscuro: "#244A80",
  azulMedio: "#2E7ABE",
  teal: "#60BFB8",
  white: "#FFFFFF",
  textSecondary: "#666666",
  border: "#E0E0E0",
  gradient: "linear-gradient(90deg, #60BFB8 0%, #2E7ABE 25%, #244A80 50%, #963058 75%, #E96A73 100%)",
};

/**
 * Storyboard Generator — full frontend flow
 * Screens: Upload → Review/Edit → Graphic Selection → (Generate pptx)
 *
 * Talks to:
 *   POST /upload-pdf      (multipart/form-data, field name "pdf")
 *   POST /generate-pptx   (application/json, { storyboard })
 *
 * Adjust API_BASE to your backend's URL.
 */

// Same-origin API — frontend and backend are served by the same Express
// app in production, so no absolute URL or env var is needed.
const API_BASE = "/api";

// Set to true only if you want to click through the UI without a live
// backend/API key configured (useful for local UI work). In the deployed
// app this should stay false so it talks to the real server.
const DEMO_MODE = false;



function buildMockPptPlan({ epigraphs, unit, afo, avatar }) {
  const slides = [
    { n: 1, section: "title", title: unit, subtitle: afo, bullets: [], graphicType: "none", graphicData: {} },
    { n: 2, section: "entrada", title: "What you will learn", bullets: ["Overview of key concepts", "Practical applications", "Tools and frameworks"], graphicType: "none", graphicData: {} },
  ];
  epigraphs.slice(0, 3).forEach((ep, i) => {
    slides.push({ n: slides.length + 1, section: "conceptos", title: ep, bullets: ["Core idea one", "Core idea two", "Core idea three"], graphicType: "three_node_sequence", graphicData: { nodes: ["Discover", "Apply", "Review"] } });
  });
  epigraphs.slice(3, Math.min(epigraphs.length, 6)).forEach((ep, i) => {
    slides.push({ n: slides.length + 1, section: "puntos_clave", title: ep, bullets: ["Key takeaway one", "Key takeaway two"], graphicType: "none", graphicData: {} });
  });
  const total = slides.length + 2;
  slides.push({ n: total - 1, section: "resumen", title: "Summary", bullets: ["Main idea recap", "Second key point", "What comes next"], graphicType: "none", graphicData: {} });
  slides.push({ n: total, section: "cierre", title: "Now it's your turn", bullets: ["Complete the activity in this unit", "Apply what you've learned"], graphicType: "none", graphicData: {} });
  return { unit, afo, avatar: avatar || null, totalSlides: slides.length, estimatedDuration: "5:00 min", wordTarget: 750, epigraphs, slides };
}

function buildMockPptResult(plan) {
  const scriptSlides = (plan.slides || []).map((s) => ({
    n: s.n,
    section: s.section,
    script: s.section === "title"
      ? "[No narration — silent or ambient sound only]"
      : s.section === "entrada"
        ? `Welcome. Today we're going to explore ${plan.unit}. By the end of this video, you'll have a clear understanding of the key ideas and how to apply them. [pause] Let's get started.`
        : s.section === "resumen"
          ? `Let's take a moment to consolidate what we've covered. ${(s.bullets || []).join(". ")}. [pause] These are the foundations you'll keep coming back to.`
          : s.section === "cierre"
            ? `That's it for this unit. Head to the activity in the platform and put these ideas into practice. You've got this.`
            : `${s.title} is one of the key areas we need to understand here. ${(s.bullets || []).join(". ")}. [pause] These aren't abstract ideas — they directly shape how you work with this content in real situations.`,
    productionNotes: s.section === "title" ? "Silent. 3–4 seconds." : "Measured, conversational pace.",
  }));
  const educalab = {
    en: {
      name: plan.unit,
      shortDescription: `An overview of ${plan.unit} covering the key concepts and practical takeaways for learners.`,
      tags: ["instructional design", "higher education", "video tutorial", "learning", "educa edtech"],
      longDescription: `This video for ${plan.afo} covers the main topics of ${plan.unit}. Learners will explore core concepts, key frameworks, and practical applications. By the end, they will be able to identify and apply the ideas presented in real-world contexts. This video is designed as a concise, engaging introduction suitable for adult learners in online higher education.`,
    },
    es: {
      name: plan.unit,
      shortDescription: `Una introducción a ${plan.unit} que cubre los conceptos clave y los aprendizajes prácticos para el alumno.`,
      tags: ["diseño instruccional", "educación superior", "videotutorial", "aprendizaje", "educa edtech"],
      longDescription: `Este vídeo del módulo ${plan.afo} cubre los principales temas de ${plan.unit}. El alumnado explorará conceptos fundamentales, marcos de referencia clave y aplicaciones prácticas. Al finalizar, podrá identificar y aplicar las ideas presentadas en contextos reales. Este vídeo está diseñado como una introducción concisa y atractiva para adultos en formación online.`,
    },
  };
  const dummyBlob = new Blob(["[DEMO — real .pptx generated by backend]"], { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" });
  const blobUrl = URL.createObjectURL(dummyBlob);
  return { educalab, scriptSlides, blobUrl, fileName: `${buildUnitFileName(plan)}.pptx`, plan };
}


const PPT_SCREENS = { INPUT: "ppt_input", PLAN: "ppt_plan", RESULT: "ppt_result" };

export default function App() {
  const [pptScreen, setPptScreen] = useState(PPT_SCREENS.INPUT);
  const [pptPlan, setPptPlan] = useState(null);
  const [pptResult, setPptResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ── PPT + Script handlers ─────────────────────────────────
  const handlePdfUpload = useCallback(async (file) => {
    setLoading(true);
    setError(null);

    if (DEMO_MODE) {
      await new Promise((r) => setTimeout(r, 1400));
      setPptPlan(buildMockPptPlan({ epigraphs: ["Introduction", "SMART Framework", "Bloom's Taxonomy", "Prompt Engineering"], unit: file.name.replace(".pdf", ""), afo: "MC-B1 · Instructional Design with AI" }));
      setPptScreen(PPT_SCREENS.PLAN);
      setLoading(false);
      return;
    }

    try {
      const formData = new FormData();
      formData.append("pdf", file);
      const res = await fetch(`${API_BASE}/pdf-to-plan`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const plan = await res.json();
      setPptPlan(plan);
      setPptScreen(PPT_SCREENS.PLAN);
    } catch (e) {
      setError(e.message === "Failed to fetch"
        ? "Could not reach the backend. Is the server running?"
        : e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleManualPlan = useCallback(async ({ unit, afo, avatar, epigraphs }) => {
    setLoading(true);
    setError(null);

    if (DEMO_MODE) {
      await new Promise((r) => setTimeout(r, 1000));
      setPptPlan(buildMockPptPlan({ epigraphs, unit, afo, avatar }));
      setPptScreen(PPT_SCREENS.PLAN);
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/ppt-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unit, afo, avatar: avatar || null, epigraphs }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const plan = await res.json();
      setPptPlan(plan);
      setPptScreen(PPT_SCREENS.PLAN);
    } catch (e) {
      setError(e.message === "Failed to fetch"
        ? "Could not reach the backend. Is the server running?"
        : e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handlePptGenerate = useCallback(async (approvedPlan) => {
    setLoading(true);
    setError(null);

    if (DEMO_MODE) {
      await new Promise((r) => setTimeout(r, 1800));
      setPptResult(buildMockPptResult(approvedPlan));
      setPptScreen(PPT_SCREENS.RESULT);
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/ppt-generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: approvedPlan }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);

      const educalabRaw = res.headers.get("X-Educalab-Meta");
      const scriptRaw = res.headers.get("X-Script-Data");
      const educalab = educalabRaw ? JSON.parse(atob(educalabRaw)) : null;
      const scriptSlides = scriptRaw ? JSON.parse(atob(scriptRaw)) : [];

      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const fileName = `${buildUnitFileName(approvedPlan)}.pptx`;

      setPptResult({ educalab, scriptSlides, blobUrl, fileName, plan: approvedPlan });
      setPptScreen(PPT_SCREENS.RESULT);
    } catch (e) {
      setError(e.message === "Failed to fetch"
        ? "Could not reach the backend. Is the server running?"
        : e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const resetPpt = useCallback(() => {
    setPptPlan(null);
    setPptResult(null);
    setPptScreen(PPT_SCREENS.INPUT);
    setError(null);
  }, []);

  // ── Render ────────────────────────────────────────────────
  return (
    <div style={styles.app}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;700&family=Lato:wght@400;700&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
      <TopBar screen={pptScreen} />
      <main style={styles.main}>
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {pptScreen === PPT_SCREENS.INPUT && (
          <UploadScreen onUpload={handlePdfUpload} onManualSubmit={handleManualPlan} loading={loading} />
        )}
        {pptScreen === PPT_SCREENS.PLAN && pptPlan && (
          <PptPlanScreen
            plan={pptPlan}
            onPlanChange={setPptPlan}
            onBack={() => setPptScreen(PPT_SCREENS.INPUT)}
            onApprove={handlePptGenerate}
            loading={loading}
          />
        )}
        {pptScreen === PPT_SCREENS.RESULT && pptResult && (
          <PptResultScreen result={pptResult} onStartOver={resetPpt} />
        )}
      </main>
      <div style={styles.footerGradientBar} />
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   MODE SELECTOR — shown on first load
────────────────────────────────────────────────────────── */
/* ──────────────────────────────────────────────────────────
   TOP BAR / PROGRESS
────────────────────────────────────────────────────────── */
function TopBar({ screen }) {
  const steps = [
    { key: PPT_SCREENS.INPUT, label: "Input" },
    { key: PPT_SCREENS.PLAN, label: "Plan" },
    { key: PPT_SCREENS.RESULT, label: "Result" },
  ];
  const activeIndex = steps.findIndex((s) => s.key === screen);

  return (
    <header style={styles.topbar}>
      <div style={styles.brand}>
        <span style={styles.brandMark}>EE</span>
        <span style={styles.brandText}>EDUCA EDTECH Group — PPT + Script</span>
      </div>
      <div style={styles.steps}>
        {steps.map((s, i) => (
          <div key={s.key} style={styles.stepItem}>
            <span style={{ ...styles.stepDot, background: i <= activeIndex ? BRAND.burdeos : BRAND.border }} />
            <span style={{ ...styles.stepLabel, color: i <= activeIndex ? BRAND.negro : BRAND.textSecondary }}>{s.label}</span>
            {i < steps.length - 1 && <span style={styles.stepLine} />}
          </div>
        ))}
      </div>
      <div style={styles.topbarGradient} />
    </header>
  );
}

/* ──────────────────────────────────────────────────────────
   SCREEN 1 — UPLOAD PDF
────────────────────────────────────────────────────────── */
function UploadScreen({ onUpload, onManualSubmit, loading }) {
  const [mode, setMode] = useState("pdf"); // "pdf" | "manual"
  const [dragOver, setDragOver] = useState(false);
  const [unit, setUnit] = useState("");
  const [afo, setAfo] = useState("");
  const [avatar, setAvatar] = useState("");
  const [epigraphsText, setEpigraphsText] = useState("");

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type === "application/pdf") onUpload(file);
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    const epigraphs = epigraphsText.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!unit || !afo || epigraphs.length === 0) return;
    onManualSubmit({ unit, afo, avatar, epigraphs });
  };

  return (
    <div style={styles.centeredScreen}>
      <div style={styles.heroBlock}>
        <span style={styles.eyebrow}>Step 1 of 3</span>
        <h1 style={styles.h1}>{mode === "pdf" ? "Upload the course unit PDF" : "Enter the unit epigraphs"}</h1>
        <p style={styles.lead}>
          {mode === "pdf"
            ? "Drop the temario or training material PDF. The AI will extract the content, propose an 8–10 slide plan, and wait for your approval before generating anything."
            : "Type the unit's epigraph titles (e.g. transcribed from an image). The AI will propose an 8–10 slide plan and wait for your approval."}
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 18, justifyContent: "center" }}>
          <button
            style={{ ...styles.graphicChip, ...(mode === "pdf" ? styles.graphicChipActive : {}) }}
            onClick={() => setMode("pdf")}
          >
            From PDF
          </button>
          <button
            style={{ ...styles.graphicChip, ...(mode === "manual" ? styles.graphicChipActive : {}) }}
            onClick={() => setMode("manual")}
          >
            Type epigraphs
          </button>
        </div>
      </div>

      {mode === "pdf" ? (
        <div
          style={{
            ...styles.dropzone,
            borderColor: dragOver ? BRAND.burdeos : BRAND.border,
            background: dragOver ? "rgba(150,48,88,0.04)" : "#FAFAFA",
          }}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          {loading ? (
            <>
              <Spinner />
              <p style={styles.dropText}>Reading the document and drafting the slide plan…</p>
              <p style={styles.dropSubtext}>This usually takes 15–30 seconds.</p>
            </>
          ) : (
            <>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke={BRAND.border} strokeWidth="1.5">
                <path d="M12 16V4M12 4l-4 4M12 4l4 4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M4 16v3a2 2 0 002 2h12a2 2 0 002-2v-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p style={styles.dropText}>Drag and drop your PDF here</p>
              <p style={styles.dropSubtext}>or</p>
              <label style={styles.browseBtn}>
                Browse files
                <input type="file" accept="application/pdf" style={{ display: "none" }}
                  onChange={(e) => e.target.files[0] && onUpload(e.target.files[0])} />
              </label>
              <p style={{ ...styles.dropSubtext, marginTop: 8 }}>PDF only · max one unit per upload</p>
            </>
          )}
        </div>
      ) : (
        <form onSubmit={handleManualSubmit} style={{ width: "100%", maxWidth: 560, textAlign: "left" }}>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Unit name</label>
            <input style={styles.formInput} value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="e.g. Marketing Digital — Unit 2" required />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Action formativa / Module (AFO)</label>
            <input style={styles.formInput} value={afo} onChange={(e) => setAfo(e.target.value)} placeholder="e.g. MC-MarketingDigital" required />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Avatar (optional)</label>
            <input style={styles.formInput} value={avatar} onChange={(e) => setAvatar(e.target.value)} placeholder="e.g. HeyGen avatar name" />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Epigraphs (one per line)</label>
            <textarea
              style={{ ...styles.formInput, minHeight: 140, resize: "vertical", fontFamily: "'Lato', sans-serif" }}
              value={epigraphsText}
              onChange={(e) => setEpigraphsText(e.target.value)}
              placeholder={"Introduction\nSMART Framework\nBloom's Taxonomy"}
              required
            />
          </div>
          <button type="submit" style={{ ...styles.primaryBtn, width: "100%", opacity: loading ? 0.5 : 1 }} disabled={loading}>
            {loading ? "Drafting the slide plan…" : "Generate slide plan →"}
          </button>
        </form>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   PPT SCREEN 2 — PLAN REVIEW & APPROVAL
────────────────────────────────────────────────────────── */
const SECTION_LABELS = {
  title: "Title", entrada: "Introduction", conceptos: "Key Concepts",
  puntos_clave: "Key Points", resumen: "Summary", cierre: "Closing",
};
const SECTION_COLORS = {
  title: BRAND.teal, entrada: BRAND.teal, conceptos: BRAND.azulOscuro,
  puntos_clave: BRAND.azulMedio, resumen: BRAND.burdeos, cierre: BRAND.rosa,
};

function PptPlanScreen({ plan, onPlanChange, onBack, onApprove, loading }) {
  const updateSlide = (n, patch) => {
    onPlanChange((prev) => ({
      ...prev,
      slides: prev.slides.map((s) => (s.n === n ? { ...s, ...patch } : s)),
    }));
  };
  const updateBullet = (n, i, val) => {
    onPlanChange((prev) => ({
      ...prev,
      slides: prev.slides.map((s) => {
        if (s.n !== n) return s;
        const bullets = [...(s.bullets || [])];
        bullets[i] = val;
        return { ...s, bullets };
      }),
    }));
  };

  return (
    <div style={styles.wideScreen}>
      <div style={styles.screenHeader}>
        <span style={styles.eyebrow}>Step 2 of 3 — Review the slide plan</span>
        <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
          <input
            style={{ ...styles.formInput, fontFamily: "'Rubik', sans-serif", fontSize: 20, fontWeight: 500, maxWidth: 360 }}
            value={plan.unit || ""}
            onChange={(e) => onPlanChange((prev) => ({ ...prev, unit: e.target.value }))}
            placeholder="Unit name"
          />
          <input
            style={{ ...styles.formInput, maxWidth: 320 }}
            value={plan.afo || ""}
            onChange={(e) => onPlanChange((prev) => ({ ...prev, afo: e.target.value }))}
            placeholder="Action formativa / Module (AFO)"
          />
        </div>
        <p style={styles.lead}>{plan.totalSlides} slides · ~{plan.estimatedDuration}</p>
        <p style={{ ...styles.lead, fontSize: 13, marginTop: 8 }}>Edit unit/module names, titles and bullets below, then approve to generate the .pptx + script + EducaLab metadata.</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {(plan.slides || []).map((slide) => {
          const accentColor = SECTION_COLORS[slide.section] || BRAND.negro;
          return (
            <div key={slide.n} style={{ border: `1px solid ${BRAND.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ background: accentColor, padding: "10px 18px", display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontFamily: "'Lato', sans-serif", fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.7)" }}>SLIDE {slide.n}</span>
                <span style={{ fontFamily: "'Rubik', sans-serif", fontSize: 12, fontWeight: 500, color: "#FFFFFF", letterSpacing: "0.06em", textTransform: "uppercase" }}>{SECTION_LABELS[slide.section] || slide.section}</span>
              </div>
              <div style={{ padding: "14px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
                <input
                  style={{ ...styles.formInput, fontSize: 14, fontWeight: 500 }}
                  value={slide.title || ""}
                  onChange={(e) => updateSlide(slide.n, { title: e.target.value })}
                  placeholder="Slide title"
                />
                {(slide.subtitle !== undefined && slide.section === "title") && (
                  <input
                    style={{ ...styles.formInput, fontSize: 13, color: BRAND.textSecondary }}
                    value={slide.subtitle || ""}
                    onChange={(e) => updateSlide(slide.n, { subtitle: e.target.value })}
                    placeholder="Subtitle (title slide)"
                  />
                )}
                {(slide.bullets || []).map((b, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 6, height: 6, borderRadius: 1, background: accentColor, flexShrink: 0 }} />
                    <input
                      style={{ ...styles.formInput, fontSize: 13, flex: 1 }}
                      value={b}
                      onChange={(e) => updateBullet(slide.n, i, e.target.value)}
                    />
                  </div>
                ))}
                {slide.graphicType && slide.graphicType !== "none" && (
                  <p style={{ margin: 0, fontFamily: "'Lato', sans-serif", fontSize: 11, color: BRAND.textSecondary, fontStyle: "italic" }}>Graphic: {slide.graphicType.replace(/_/g, " ")}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div style={styles.footerBar}>
        <button style={styles.secondaryBtn} onClick={onBack}>← Back to input</button>
        <button style={{ ...styles.primaryBtn, opacity: loading ? 0.5 : 1 }} onClick={() => onApprove(plan)} disabled={loading}>
          {loading ? "Generating PPT + script…" : "Approve & generate →"}
        </button>
      </div>
      {loading && (
        <div style={{ marginTop: 20, display: "flex", alignItems: "center", gap: 12, color: BRAND.textSecondary, fontFamily: "'Lato', sans-serif", fontSize: 13 }}>
          <Spinner />
          <span>The AI is writing the scripts and building the .pptx… (~20–40 seconds)</span>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   PPT SCREEN 3 — RESULT (download + script + EducaLab)
────────────────────────────────────────────────────────── */
function PptResultScreen({ result, onStartOver }) {
  const { educalab, scriptSlides, blobUrl, fileName, plan } = result;
  const [lang, setLang] = useState("en");
  const [copied, setCopied] = useState(null);
  const meta = educalab?.[lang] || {};

  const copyField = (key, value) => {
    const text = Array.isArray(value) ? value.join(", ") : value;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1800);
    });
  };

  return (
    <div style={styles.wideScreen}>
      <div style={styles.screenHeader}>
        <span style={styles.eyebrow}>Step 3 of 3 — Done</span>
        <h1 style={styles.h1}>{plan.unit}</h1>
        <p style={styles.lead}>{plan.totalSlides} slides · ~{plan.estimatedDuration}</p>
      </div>

      {/* Download */}
      <div style={{ padding: "24px 28px", borderRadius: 10, border: `1px solid ${BRAND.border}`, marginBottom: 28, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
        <div>
          <div style={{ fontFamily: "'Rubik', sans-serif", fontSize: 15, fontWeight: 500, color: BRAND.negro, marginBottom: 4 }}>Corporate PPT ready</div>
          <div style={{ fontFamily: "'Lato', sans-serif", fontSize: 12, color: BRAND.textSecondary }}>{fileName}</div>
        </div>
        <a href={blobUrl} download={fileName} style={styles.downloadBtn}>⬇ Download .pptx</a>
      </div>

      {/* Avatar scripts */}
      <div style={{ marginBottom: 28 }}>
        <h2 style={{ fontFamily: "'Rubik', sans-serif", fontSize: 17, fontWeight: 500, color: BRAND.negro, marginBottom: 16, paddingBottom: 8, borderBottom: `2px solid ${BRAND.burdeos}` }}>Avatar Script — slide by slide</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(scriptSlides || []).map((s) => {
            const slideData = (plan.slides || []).find((p) => p.n === s.n) || {};
            const accentColor = SECTION_COLORS[slideData.section] || BRAND.negro;
            return (
              <div key={s.n} style={{ borderRadius: 8, border: `1px solid ${BRAND.border}`, overflow: "hidden" }}>
                <div style={{ padding: "8px 16px", background: accentColor, display: "flex", gap: 10, alignItems: "center" }}>
                  <span style={{ fontFamily: "'Lato', sans-serif", fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.8)" }}>SLIDE {s.n}</span>
                  <span style={{ fontFamily: "'Rubik', sans-serif", fontSize: 12, color: "#FFFFFF" }}>{slideData.title || SECTION_LABELS[slideData.section] || ""}</span>
                </div>
                <div style={{ padding: "12px 16px" }}>
                  <p style={{ fontFamily: "'Lato', sans-serif", fontSize: 14, color: BRAND.negro, lineHeight: 1.65, margin: "0 0 8px" }}>{s.script}</p>
                  {s.productionNotes && (
                    <p style={{ fontFamily: "'Lato', sans-serif", fontSize: 11, color: BRAND.textSecondary, margin: 0, fontStyle: "italic" }}>📝 {s.productionNotes}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* EducaLab metadata */}
      {educalab && (
        <div style={{ marginBottom: 40 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, paddingBottom: 8, borderBottom: `2px solid ${BRAND.burdeos}` }}>
            <h2 style={{ fontFamily: "'Rubik', sans-serif", fontSize: 17, fontWeight: 500, color: BRAND.negro, margin: 0 }}>EducaLab Metadata</h2>
            <div style={{ display: "flex", gap: 6 }}>
              {["en", "es"].map((l) => (
                <button key={l} style={{ padding: "4px 12px", borderRadius: 9999, border: `1px solid ${lang === l ? BRAND.burdeos : BRAND.border}`, background: lang === l ? BRAND.burdeos : "transparent", color: lang === l ? "#FFFFFF" : BRAND.textSecondary, fontFamily: "'Lato', sans-serif", fontSize: 11, fontWeight: 700, cursor: "pointer" }} onClick={() => setLang(l)}>{l.toUpperCase()}</button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[
              { key: "name", label: "Name" },
              { key: "shortDescription", label: "Short description" },
              { key: "tags", label: "Tags" },
              { key: "longDescription", label: "Long description" },
            ].map(({ key, label }) => {
              const value = meta[key];
              const display = Array.isArray(value) ? value.join(", ") : value || "—";
              return (
                <div key={key} style={{ border: `1px solid ${BRAND.border}`, borderRadius: 8, padding: "12px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontFamily: "'Lato', sans-serif", fontSize: 10, fontWeight: 700, color: BRAND.burdeos, textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
                    <button style={{ background: "none", border: "none", color: copied === key ? BRAND.teal : BRAND.textSecondary, fontFamily: "'Lato', sans-serif", fontSize: 11, cursor: "pointer" }} onClick={() => copyField(key, value)}>{copied === key ? "✓ Copied" : "Copy"}</button>
                  </div>
                  <p style={{ fontFamily: "'Lato', sans-serif", fontSize: 13, color: BRAND.negro, margin: 0, lineHeight: 1.6 }}>{display}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ textAlign: "center" }}>
        <button style={styles.linkBtn} onClick={onStartOver}>Start over with a new PDF</button>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   SMALL COMPONENTS
────────────────────────────────────────────────────────── */
function ErrorBanner({ message, onDismiss }) {
  return (
    <div style={styles.errorBanner}>
      <span>⚠ {message}</span>
      <button style={styles.errorDismiss} onClick={onDismiss}>✕</button>
    </div>
  );
}

function Spinner() {
  return <div style={styles.spinner} />;
}


function slugify(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// File naming convention (manual §13): MC-[AFO]-[Unidad], e.g. "MC-MarketingDigital-U2"
function buildUnitFileName(plan) {
  const clean = (s) => (s || "").replace(/[^a-zA-Z0-9]+/g, "");
  return `MC-${clean(plan.afo) || "AFO"}-${clean(plan.unit) || "Unidad"}`;
}

/* ──────────────────────────────────────────────────────────
   STYLES — EDUCA EDTECH Group brand system
   Negro #202020 · Burdeos #963058 · Rosa #E96A73
   Azul Oscuro #244A80 · Azul Medio #2E7ABE · Teal #60BFB8
   Headings: Rubik · Body: Lato
────────────────────────────────────────────────────────── */
const styles = {
  app: {
    minHeight: "100vh",
    background: BRAND.white,
    color: BRAND.negro,
    fontFamily: "'Lato', 'Calibri', sans-serif",
  },
  main: { maxWidth: 980, margin: "0 auto", padding: "0 32px 80px" },

  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "20px 32px",
    borderBottom: `1px solid ${BRAND.border}`,
    position: "relative",
  },
  // Gradient hairline under the topbar — brand rule: gradient line at
  // header/footer or section breaks
  topbarGradient: {
    position: "absolute",
    bottom: -2,
    left: 0,
    right: 0,
    height: 2,
    background: BRAND.gradient,
  },
  brand: { display: "flex", alignItems: "center", gap: 10 },
  brandMark: {
    width: 22, height: 22, borderRadius: 5,
    background: BRAND.negro, color: BRAND.white,
    display: "flex", alignItems: "center", justifyContent: "center",
    fontFamily: "'Rubik', sans-serif", fontWeight: 500, fontSize: 11,
  },
  brandText: {
    fontFamily: "'Rubik', sans-serif",
    fontSize: 14, fontWeight: 500, letterSpacing: "0.01em", color: BRAND.negro,
  },

  steps: { display: "flex", alignItems: "center", gap: 8 },
  stepItem: { display: "flex", alignItems: "center", gap: 8 },
  stepDot: { width: 6, height: 6, borderRadius: "50%", transition: "background 200ms" },
  stepLabel: { fontSize: 11, fontFamily: "'Lato', sans-serif", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" },
  stepLine: { width: 24, height: 1, background: BRAND.border },

  centeredScreen: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    paddingTop: 80,
    gap: 40,
  },
  wideScreen: { paddingTop: 56 },

  heroBlock: { maxWidth: 560 },
  screenHeader: { maxWidth: 640, marginBottom: 40 },
  eyebrow: {
    display: "block",
    fontFamily: "'Lato', sans-serif",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: BRAND.burdeos,
    marginBottom: 14,
  },
  h1: {
    fontFamily: "'Rubik', sans-serif",
    fontSize: 32,
    fontWeight: 500,
    letterSpacing: "-0.01em",
    lineHeight: 1.2,
    color: BRAND.negro,
    margin: "0 0 14px",
  },
  lead: {
    fontFamily: "'Lato', sans-serif",
    fontSize: 16,
    fontWeight: 400,
    lineHeight: 1.6,
    color: BRAND.textSecondary,
    margin: 0,
  },

  dropzone: {
    width: "100%",
    maxWidth: 560,
    minHeight: 280,
    border: `1.5px dashed ${BRAND.border}`,
    borderRadius: 12,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    transition: "all 200ms ease",
    padding: 40,
    background: "#FAFAFA",
  },
  dropText: { fontFamily: "'Rubik', sans-serif", fontSize: 15, fontWeight: 500, margin: 0, color: BRAND.negro },
  dropSubtext: { fontFamily: "'Lato', sans-serif", fontSize: 13, color: BRAND.textSecondary, margin: 0 },
  browseBtn: {
    marginTop: 4,
    padding: "10px 24px",
    borderRadius: 6,
    background: BRAND.burdeos,
    color: BRAND.white,
    fontFamily: "'Rubik', sans-serif",
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  },

  spinner: {
    width: 32,
    height: 32,
    border: `2px solid ${BRAND.border}`,
    borderTopColor: BRAND.burdeos,
    borderRadius: "50%",
    animation: "spin 800ms linear infinite",
  },

  sectionList: { display: "flex", flexDirection: "column", gap: 28 },
  sectionGroup: { display: "flex", flexDirection: "column", gap: 10 },
  sectionGroupHeader: {
    fontFamily: "'Rubik', sans-serif",
    fontSize: 12,
    fontWeight: 500,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: BRAND.negro,
    paddingBottom: 8,
    borderBottom: `2px solid ${BRAND.burdeos}`,
  },
  sceneList: { display: "flex", flexDirection: "column", gap: 12 },

  sceneCard: {
    border: `1px solid ${BRAND.border}`,
    borderRadius: 8,
    padding: "20px 24px",
    background: BRAND.white,
  },
  graphicCard: {
    border: `1px solid ${BRAND.border}`,
    borderRadius: 8,
    padding: "20px 24px",
    background: BRAND.white,
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  sceneCardHeader: { display: "flex", gap: 16, alignItems: "flex-start" },
  sceneCardMuted: { background: "#FAFAFA", borderStyle: "dashed" },
  sceneNum: {
    fontFamily: "'Lato', sans-serif",
    fontSize: 12,
    fontWeight: 700,
    color: BRAND.textSecondary,
    paddingTop: 2,
  },
  sceneTitle: { fontFamily: "'Rubik', sans-serif", fontSize: 15, fontWeight: 500, marginBottom: 4, color: BRAND.negro },
  sceneTitleDim: { fontWeight: 400, color: BRAND.textSecondary },
  sceneMeta: {
    fontFamily: "'Lato', sans-serif",
    fontSize: 11,
    fontWeight: 400,
    color: BRAND.textSecondary,
  },
  sceneTypeBadge: {
    fontFamily: "'Lato', sans-serif",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    padding: "4px 10px",
    borderRadius: 9999,
    flexShrink: 0,
  },
  sceneTypeBadgeMuted: { background: "#F0F0F0", color: BRAND.textSecondary },
  sceneTypeBadgeActive: { background: "rgba(150,48,88,0.1)", color: BRAND.burdeos },

  scriptTextarea: {
    width: "100%",
    marginTop: 14,
    padding: 14,
    borderRadius: 6,
    border: `1px solid ${BRAND.border}`,
    background: "#FAFAFA",
    color: BRAND.negro,
    fontSize: 14,
    lineHeight: 1.6,
    fontFamily: "'Lato', sans-serif",
    resize: "vertical",
  },

  graphicOptions: { display: "flex", flexWrap: "wrap", gap: 8 },
  graphicChip: {
    padding: "8px 14px",
    borderRadius: 9999,
    border: `1px solid ${BRAND.border}`,
    background: "transparent",
    color: BRAND.textSecondary,
    fontFamily: "'Lato', sans-serif",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    transition: "all 150ms ease",
  },
  graphicChipActive: {
    background: BRAND.burdeos,
    borderColor: BRAND.burdeos,
    color: BRAND.white,
  },

  footerBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 40,
    paddingTop: 24,
    borderTop: `1px solid ${BRAND.border}`,
  },
  footerHint: { fontFamily: "'Lato', sans-serif", fontSize: 12, color: BRAND.textSecondary },

  primaryBtn: {
    padding: "12px 26px",
    borderRadius: 6,
    background: BRAND.burdeos,
    color: BRAND.white,
    fontFamily: "'Rubik', sans-serif",
    fontSize: 14,
    fontWeight: 500,
    border: "none",
    cursor: "pointer",
  },
  secondaryBtn: {
    padding: "12px 26px",
    borderRadius: 6,
    background: "transparent",
    color: BRAND.negro,
    fontFamily: "'Rubik', sans-serif",
    fontSize: 14,
    fontWeight: 500,
    border: `1px solid ${BRAND.border}`,
    cursor: "pointer",
  },
  downloadBtn: {
    display: "inline-block",
    padding: "16px 34px",
    borderRadius: 8,
    background: BRAND.burdeos,
    color: BRAND.white,
    fontFamily: "'Rubik', sans-serif",
    fontSize: 15,
    fontWeight: 500,
    textDecoration: "none",
  },
  demoNotice: {
    maxWidth: 420,
    padding: "16px 20px",
    borderRadius: 8,
    background: "rgba(150,48,88,0.06)",
    border: "1px solid rgba(150,48,88,0.2)",
    color: BRAND.negro,
    fontFamily: "'Lato', sans-serif",
    fontSize: 13,
    lineHeight: 1.6,
  },
  linkBtn: {
    background: "none",
    border: "none",
    color: BRAND.textSecondary,
    fontFamily: "'Lato', sans-serif",
    fontSize: 13,
    cursor: "pointer",
    textDecoration: "underline",
  },

  errorBanner: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderRadius: 6,
    background: "rgba(233,106,105,0.08)",
    border: "1px solid rgba(233,106,105,0.3)",
    color: BRAND.rosa,
    fontFamily: "'Lato', sans-serif",
    fontSize: 13,
    marginTop: 24,
  },
  errorDismiss: {
    background: "none",
    border: "none",
    color: "inherit",
    cursor: "pointer",
    fontSize: 13,
  },

  formGroup: { display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 },
  formLabel: {
    fontFamily: "'Lato', sans-serif", fontSize: 11, fontWeight: 700,
    color: BRAND.negro, letterSpacing: "0.06em", textTransform: "uppercase",
  },
  formInput: {
    padding: "10px 14px", borderRadius: 6, border: `1px solid ${BRAND.border}`,
    background: "#FAFAFA", color: BRAND.negro, fontSize: 15,
    fontFamily: "'Lato', sans-serif", outline: "none", width: "100%",
    boxSizing: "border-box",
  },

  // Gradient bar — brand rule: flush to slide/section bottom edge,
  // used here as a footer accent across the whole app
  footerGradientBar: {
    height: 4,
    width: "100%",
    background: BRAND.gradient,
    marginTop: 60,
  },
};
