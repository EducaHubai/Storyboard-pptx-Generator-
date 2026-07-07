/**
 * Storyboard Generator — unified server
 *
 * Serves the React frontend (built static files) AND the API endpoints
 * from the same Express app / same port, so Coolify only needs to run
 * ONE service.
 *
 *   POST /api/upload-pdf      → PDF in, storyboard JSON out
 *   POST /api/generate-pptx   → storyboard JSON in, .pptx file out
 *   GET  /*                   → React app (client/build)
 */

const express = require("express");
const multer = require("multer");
const fs = require("fs");
const path = require("path");
const OpenAI = require("openai");
const pdfParse = require("pdf-parse");
const pptxgen = require("pptxgenjs");
const JSZip = require("jszip");

const app = express();
app.use(express.json({ limit: "10mb" }));

const upload = multer({ dest: "/tmp/uploads" });

if (!process.env.OPENAI_API_KEY) {
  console.warn("⚠ OPENAI_API_KEY is not set. API endpoints will fail until configured.");
}
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

async function callOpenAI(systemPrompt, userContent, maxTokens = 4000) {
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    max_tokens: maxTokens,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userContent },
    ],
  });
  const raw = response.choices[0].message.content || "";
  return raw.replace(/^```json\s*|\s*```$/g, "").trim();
}

const SYSTEM_PROMPT = fs.readFileSync(
  path.join(__dirname, "system-prompt-upload-pdf.md"),
  "utf-8"
);
const SCHEMA = fs.readFileSync(
  path.join(__dirname, "storyboard.schema.json"),
  "utf-8"
);
const PPT_PLAN_PROMPT = fs.readFileSync(
  path.join(__dirname, "system-prompt-ppt-plan.md"),
  "utf-8"
);
const PPT_GENERATE_PROMPT = fs.readFileSync(
  path.join(__dirname, "system-prompt-ppt-generate.md"),
  "utf-8"
);
const PDF_TO_PLAN_PROMPT = fs.readFileSync(
  path.join(__dirname, "system-prompt-pdf-to-plan.md"),
  "utf-8"
);

// Brand fonts (Rubik, Lato — OFL licensed) embedded into generated .pptx
// files so headings/body render correctly on machines that don't have
// them installed (§6.4 of the manual), instead of silently falling back
// to a substitute font.
const FONTS_DIR = path.join(__dirname, "fonts");
const BRAND_FONTS = [
  { typeface: "Rubik", style: "regular", file: "Rubik-Regular.ttf" },
  { typeface: "Rubik", style: "bold", file: "Rubik-Bold.ttf" },
  { typeface: "Lato", style: "regular", file: "Lato-Regular.ttf" },
  { typeface: "Lato", style: "bold", file: "Lato-Bold.ttf" },
].map((f) => ({ ...f, buffer: fs.readFileSync(path.join(FONTS_DIR, f.file)) }));

// ────────────────────────────────────────────────────────────
// Health check — useful for Coolify / uptime monitors
// ────────────────────────────────────────────────────────────
app.get("/api/health", (req, res) => {
  res.json({ ok: true, openaiConfigured: Boolean(process.env.OPENAI_API_KEY) });
});

app.get("/api/test-openai", async (req, res) => {
  try {
    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      max_tokens: 20,
      messages: [{ role: "user", content: "Say hi" }],
    });
    res.json({ ok: true, response: response.choices[0].message.content });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message, status: err.status });
  }
});

// ────────────────────────────────────────────────────────────
// POST /api/upload-pdf
// ────────────────────────────────────────────────────────────
app.post("/api/upload-pdf", upload.single("pdf"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No PDF file received (field name must be 'pdf')." });
    }
    if (!process.env.OPENAI_API_KEY) {
      return res.status(500).json({ error: "Server is missing OPENAI_API_KEY." });
    }

    const pdfBuffer = fs.readFileSync(req.file.path);
    const { text: pdfText } = await pdfParse(pdfBuffer);
    fs.unlink(req.file.path, () => {});

    const systemWithSchema = SYSTEM_PROMPT.replace(
      "<insert contents of storyboard.schema.json here>",
      SCHEMA
    );
    const raw = await callOpenAI(
      systemWithSchema,
      `Generate the storyboard JSON for this course unit:\n\n${pdfText.slice(0, 14000)}`,
      8000
    );
    const storyboard = JSON.parse(raw);

    res.json(storyboard);
  } catch (err) {
    console.error("upload-pdf error:", err);
    res.status(500).json({ error: "Failed to generate storyboard", detail: err.message });
  }
});

// ────────────────────────────────────────────────────────────
// POST /api/generate-pptx
// ────────────────────────────────────────────────────────────
app.post("/api/generate-pptx", async (req, res) => {
  try {
    const { storyboard } = req.body;
    if (!storyboard) {
      return res.status(400).json({ error: "Missing 'storyboard' in request body." });
    }

    const pres = new pptxgen();
    pres.layout = "LAYOUT_16x9";
    pres.title = storyboard.meta.title;

    const paletteMap = {};
    (storyboard.meta.sectionPalette || []).forEach((p) => {
      paletteMap[p.section] = p.hex.replace("#", "");
    });

    storyboard.scenes.forEach((scene) => {
      const slide = pres.addSlide();
      const sectionColor = paletteMap[scene.section] || "202020";

      if (scene.type === "title_card") {
        renderTitleCard(slide, scene, sectionColor);
      } else {
        renderContentScene(slide, scene, sectionColor);
      }

      slide.addNotes(scene.script || "");
    });

    const outPath = `/tmp/storyboard-${Date.now()}.pptx`;
    await pres.writeFile({ fileName: outPath });

    res.download(outPath, `${slugify(storyboard.meta.title)}.pptx`, () => {
      fs.unlink(outPath, () => {});
    });
  } catch (err) {
    console.error("generate-pptx error:", err);
    res.status(500).json({ error: "Failed to generate pptx", detail: err.message });
  }
});

// ────────────────────────────────────────────────────────────
// POST /api/pdf-to-plan
// PDF → extract text → GPT-4o → slide plan JSON
// ────────────────────────────────────────────────────────────
app.post("/api/pdf-to-plan", upload.single("pdf"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No PDF file received (field name must be 'pdf')." });
    }
    if (!process.env.OPENAI_API_KEY) {
      return res.status(500).json({ error: "Server is missing OPENAI_API_KEY." });
    }

    const pdfBuffer = fs.readFileSync(req.file.path);
    const { text: pdfText } = await pdfParse(pdfBuffer);
    fs.unlink(req.file.path, () => {});

    const raw = await callOpenAI(
      PDF_TO_PLAN_PROMPT,
      `Here is the full content of the course unit:\n\n${pdfText.slice(0, 14000)}\n\nExtract the unit content and generate the slide plan JSON.`
    );
    const plan = JSON.parse(raw);
    res.json(plan);
  } catch (err) {
    console.error("pdf-to-plan error:", err);
    res.status(500).json({ error: "Failed to generate slide plan from PDF", detail: err.message });
  }
});

// ────────────────────────────────────────────────────────────
// POST /api/ppt-plan  (kept for potential direct use)
// Epígrafes + metadata → GPT-4o → slide plan JSON
// ────────────────────────────────────────────────────────────
app.post("/api/ppt-plan", async (req, res) => {
  try {
    const { epigraphs, unit, afo, avatar } = req.body;
    if (!epigraphs || !unit || !afo) {
      return res.status(400).json({ error: "Missing required fields: epigraphs, unit, afo." });
    }
    if (!process.env.OPENAI_API_KEY) {
      return res.status(500).json({ error: "Server is missing OPENAI_API_KEY." });
    }

    const userMessage = [
      `Unit: ${unit}`,
      `Action formativa / Module: ${afo}`,
      avatar ? `Avatar: ${avatar}` : null,
      "",
      "Epigraphs (section titles) for this unit:",
      ...epigraphs.map((e, i) => `${i + 1}. ${e}`),
    ].filter(Boolean).join("\n");

    const raw = await callOpenAI(PPT_PLAN_PROMPT, userMessage);
    const plan = JSON.parse(raw);
    res.json(plan);
  } catch (err) {
    console.error("ppt-plan error:", err);
    res.status(500).json({ error: "Failed to generate slide plan", detail: err.message });
  }
});

// ────────────────────────────────────────────────────────────
// POST /api/ppt-generate
// Approved plan → GPT-4o scripts + EducaLab metadata + .pptx download
// ────────────────────────────────────────────────────────────
app.post("/api/ppt-generate", async (req, res) => {
  try {
    const { plan } = req.body;
    if (!plan || !plan.slides) {
      return res.status(400).json({ error: "Missing 'plan' in request body." });
    }
    if (!process.env.OPENAI_API_KEY) {
      return res.status(500).json({ error: "Server is missing OPENAI_API_KEY." });
    }

    // Step 1: generate scripts + EducaLab metadata via Claude
    const raw = await callOpenAI(
      PPT_GENERATE_PROMPT,
      `Generate the avatar script and EducaLab metadata for this approved slide plan:\n\n${JSON.stringify(plan, null, 2)}`,
      6000
    );
    const generated = JSON.parse(raw);

    // Step 2: build .pptx
    const pres = new pptxgen();
    pres.layout = "LAYOUT_16x9";
    pres.title = plan.unit;

    // Merge plan slides with generated scripts
    plan.slides.forEach((slideData) => {
      const scriptData = (generated.slides || []).find((s) => s.n === slideData.n) || {};
      const slide = pres.addSlide();
      renderCorporateSlide(slide, slideData, scriptData.script || "");
      slide.addNotes(
        [scriptData.script, scriptData.productionNotes].filter(Boolean).join("\n\n---\n")
      );
    });

    const outPath = `/tmp/ppt-${Date.now()}.pptx`;
    await pres.writeFile({ fileName: outPath });

    try {
      await embedFonts(outPath);
    } catch (fontErr) {
      // Non-fatal: deliver the pptx with fontFace names set but not
      // embedded rather than failing the whole request.
      console.warn("embedFonts failed, shipping pptx without embedded fonts:", fontErr.message);
    }

    // Step 3: send pptx as download + metadata in header
    const metaHeader = Buffer.from(JSON.stringify(generated.educalab || {})).toString("base64");
    const scriptHeader = Buffer.from(JSON.stringify(generated.slides || [])).toString("base64");
    res.setHeader("X-Educalab-Meta", metaHeader);
    res.setHeader("X-Script-Data", scriptHeader);
    res.download(outPath, `${buildUnitFileName(plan)}.pptx`, () => {
      fs.unlink(outPath, () => {});
    });
  } catch (err) {
    console.error("ppt-generate error:", err);
    res.status(500).json({ error: "Failed to generate PPT", detail: err.message });
  }
});

// ────────────────────────────────────────────────────────────
// Slide renderers
// ────────────────────────────────────────────────────────────
function renderTitleCard(slide, scene, hexColor) {
  slide.background = { color: hexColor };
  slide.addText(scene.visual.onScreenText || scene.section, {
    x: 0, y: 2.2, w: 10, h: 1.2,
    fontFace: "Arial", fontSize: 44, bold: true,
    color: "FFFFFF", align: "center", valign: "middle",
  });
}

function renderContentScene(slide, scene, hexColor) {
  const bg = scene.visual.background || {};
  slide.background = { color: (bg.colors?.[0] || "FFFFFF").replace("#", "") };

  slide.addText(scene.visual.onScreenText || "", {
    x: 0.5, y: 0.4, w: 6, h: 0.8,
    fontFace: "Arial", fontSize: 24, bold: true, color: "202020",
  });

  const avatarSpace = { left: 0, right: 6.5, center: 0 }[scene.visual.avatarPosition] ?? 6.5;
  const graphicWidth = scene.visual.avatarPosition === "hidden" ? 9 : 5.8;

  renderGraphic(slide, scene.visual.graphicType, scene.visual.graphicData || {}, {
    x: scene.visual.avatarPosition === "right" ? 0.5 : avatarSpace,
    y: 1.4, w: graphicWidth, h: 3.8,
  });
}

function renderGraphic(slide, type, data, box) {
  switch (type) {
    case "before_after":
      slide.addText(`${data.beforeLabel || "Before"}: ${data.beforeText || ""}`, {
        x: box.x, y: box.y, w: box.w, h: 1, fontSize: 14, color: "963058",
      });
      slide.addText(`${data.afterLabel || "After"}: ${data.afterText || ""}`, {
        x: box.x, y: box.y + 1.2, w: box.w, h: 1.2, fontSize: 14, color: "202020",
      });
      break;

    case "smart_grid":
      (data.items || []).forEach((item, i) => {
        const col = i % 2, row = Math.floor(i / 2);
        slide.addShape("rect", {
          x: box.x + col * (box.w / 2), y: box.y + row * 0.9,
          w: box.w / 2 - 0.05, h: 0.85,
          fill: { color: item.letter === data.highlightLetter ? "963058" : "F0F0F0" },
        });
        slide.addText(item.letter, {
          x: box.x + col * (box.w / 2), y: box.y + row * 0.9,
          w: box.w / 2 - 0.05, h: 0.55, fontSize: 28, bold: true, align: "center",
          color: item.letter === data.highlightLetter ? "FFFFFF" : "666666",
        });
        slide.addText(item.word, {
          x: box.x + col * (box.w / 2), y: box.y + row * 0.9 + 0.55,
          w: box.w / 2 - 0.05, h: 0.3, fontSize: 9, align: "center", color: "666666",
        });
      });
      break;

    case "data_table": {
      const tableRows = [
        data.columns.map((c) => ({ text: c, options: { bold: true, fill: { color: "202020" }, color: "FFFFFF" } })),
        ...(data.rows || []).map((r) => r.map((cell) => ({ text: cell }))),
      ];
      slide.addTable(tableRows, { x: box.x, y: box.y, w: box.w, fontSize: 11 });
      break;
    }

    case "text_only":
      slide.addText(data.text || "", {
        x: box.x, y: box.y, w: box.w, h: box.h,
        fontFace: "Lato", fontSize: 13, color: "202020", align: "center", valign: "middle",
      });
      break;

    case "three_node_sequence": {
      const nodes = data.nodes || [];
      const n = Math.max(nodes.length, 1);
      const slotW = box.w / n;
      const nodeW = slotW - 0.18;
      nodes.forEach((label, i) => {
        const x = box.x + i * slotW;
        slide.addShape("roundRect", {
          x, y: box.y + box.h / 2 - 0.35, w: nodeW, h: 0.7, rectRadius: 0.06,
          fill: { color: "244A80" }, line: { color: "244A80" },
        });
        slide.addText(label, {
          x, y: box.y + box.h / 2 - 0.35, w: nodeW, h: 0.7,
          fontFace: "Lato", fontSize: 11, color: "FFFFFF", align: "center", valign: "middle",
        });
        if (i < n - 1) {
          slide.addText("→", {
            x: x + nodeW, y: box.y + box.h / 2 - 0.25, w: slotW - nodeW, h: 0.5,
            fontSize: 16, color: "963058", align: "center", valign: "middle",
          });
        }
      });
      break;
    }

    case "numbered_list": {
      const items = data.items || [];
      const rowH = box.h / Math.max(items.length, 1);
      items.forEach((text, i) => {
        const y = box.y + i * rowH;
        slide.addShape("ellipse", {
          x: box.x, y: y + rowH / 2 - 0.18, w: 0.36, h: 0.36,
          fill: { color: "2E7ABE" }, line: { color: "2E7ABE" },
        });
        slide.addText(String(i + 1), {
          x: box.x, y: y + rowH / 2 - 0.18, w: 0.36, h: 0.36,
          fontFace: "Rubik", fontSize: 13, bold: true, color: "FFFFFF", align: "center", valign: "middle",
        });
        slide.addText(text, {
          x: box.x + 0.5, y, w: box.w - 0.5, h: rowH,
          fontFace: "Lato", fontSize: 12, color: "202020", valign: "middle",
        });
      });
      break;
    }

    case "validation_flow": {
      const steps = data.steps || [];
      const rowH = box.h / Math.max(steps.length, 1);
      steps.forEach((text, i) => {
        const y = box.y + i * rowH;
        slide.addText("✓", {
          x: box.x, y, w: 0.4, h: rowH,
          fontSize: 16, bold: true, color: "60BFB8", align: "center", valign: "middle",
        });
        slide.addText(text, {
          x: box.x + 0.45, y, w: box.w - 0.45, h: rowH,
          fontFace: "Lato", fontSize: 12, color: "202020", valign: "middle",
        });
      });
      break;
    }

    case "pillar_columns": {
      const cols = data.columns || [];
      const n = Math.max(cols.length, 1);
      const slotW = box.w / n;
      const colW = slotW - 0.1;
      cols.forEach((col, i) => {
        const x = box.x + i * slotW;
        slide.addShape("rect", { x, y: box.y, w: colW, h: box.h, fill: { color: "F0F0F0" }, line: { color: "E0E0E0" } });
        slide.addText(col.title || "", {
          x: x + 0.08, y: box.y + 0.1, w: colW - 0.16, h: 0.4,
          fontFace: "Rubik", fontSize: 11, bold: true, color: "963058", align: "center",
        });
        slide.addText(col.text || "", {
          x: x + 0.08, y: box.y + 0.55, w: colW - 0.16, h: box.h - 0.65,
          fontFace: "Lato", fontSize: 10, color: "202020", align: "center",
        });
      });
      break;
    }

    default:
      break; // none / blooms_bars / prompt_window — unused by the active PPT+Script flow
  }
}

// Corporate PPT slide renderer — EDUCA EDTECH Group design system
const SECTION_CONFIG = {
  title:        { bg: "60BFB8", accentColor: "60BFB8", darkBg: true,  label: null },
  entrada:      { bg: "FFFFFF", accentColor: "60BFB8", darkBg: false, label: "Introduction" },
  conceptos:    { bg: "FFFFFF", accentColor: "244A80", darkBg: false, label: "Key Concepts" },
  puntos_clave: { bg: "FFFFFF", accentColor: "2E7ABE", darkBg: false, label: "Key Points" },
  resumen:      { bg: "963058", accentColor: "963058", darkBg: true,  label: null },
  cierre:       { bg: "E96A73", accentColor: "E96A73", darkBg: true,  label: null },
};

// Brand gradient stops (teal→blue-m→blue-d→burdeos→rosa). pptxgenjs has no
// native multi-stop gradient fill (unresolved upstream since 2017), so the
// bar is approximated with adjacent solid segments in this exact order.
const GRADIENT_STOPS = ["60BFB8", "2E7ABE", "244A80", "963058", "E96A73"];

function addBrandGradientBar(slide, y, h) {
  const segW = 10 / GRADIENT_STOPS.length;
  GRADIENT_STOPS.forEach((color, i) => {
    slide.addShape("rect", {
      x: i * segW, y, w: segW, h,
      fill: { color }, line: { color },
    });
  });
}

function renderCorporateSlide(slide, slideData, _script) {
  const cfg = SECTION_CONFIG[slideData.section] || SECTION_CONFIG.conceptos;
  const bullets = (slideData.bullets || []).slice(0, 3);
  const title = slideData.title || "";
  const subtitle = slideData.subtitle || null;

  slide.background = { color: cfg.bg };

  if (cfg.darkBg) {
    // Colored background slides: centered white text + gradient bar at bottom
    // Top accent strip (thin white line)
    slide.addShape("rect", {
      x: 0, y: 0, w: 10, h: 0.06,
      fill: { color: "FFFFFF" }, line: { color: "FFFFFF" },
    });

    // Title
    slide.addText(title, {
      x: 0.8, y: 1.4, w: 8.4, h: 1.8,
      fontFace: "Rubik", fontSize: 38, bold: false,
      color: "FFFFFF", align: "center", valign: "middle",
    });

    // Subtitle (only title slide)
    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.8, y: 3.2, w: 8.4, h: 0.7,
        fontFace: "Lato", fontSize: 18, color: "FFFFFF",
        align: "center", transparency: 20,
      });
    }

    // Bullets on colored slides (resumen / cierre)
    if (bullets.length > 0) {
      bullets.forEach((bullet, i) => {
        slide.addText(`• ${bullet}`, {
          x: 1.5, y: 2.8 + i * 0.72, w: 7, h: 0.65,
          fontFace: "Lato", fontSize: 18, color: "FFFFFF",
          align: "center",
        });
      });
    }

    // Brand gradient bar at bottom
    addBrandGradientBar(slide, 5.43, 0.2);
  } else {
    // Light background slides: left accent bar + title in accent color + bullets
    // Left accent bar
    slide.addShape("rect", {
      x: 0, y: 0, w: 0.14, h: 5.63,
      fill: { color: cfg.accentColor }, line: { color: cfg.accentColor },
    });

    // Section eyebrow label
    if (cfg.label) {
      slide.addText(cfg.label.toUpperCase(), {
        x: 0.36, y: 0.2, w: 9.3, h: 0.32,
        fontFace: "Lato", fontSize: 10, bold: true, color: cfg.accentColor,
        charSpacing: 2,
      });
    }

    // Title
    slide.addText(title, {
      x: 0.36, y: 0.52, w: 9.3, h: 1.0,
      fontFace: "Rubik", fontSize: 28, bold: false,
      color: cfg.accentColor,
    });

    // Hairline divider
    slide.addShape("rect", {
      x: 0.36, y: 1.52, w: 9.28, h: 0.018,
      fill: { color: "E0E0E0" }, line: { color: "E0E0E0" },
    });

    // Bullets — narrower column when a graphic panel occupies the right side
    const graphicType = slideData.graphicType && slideData.graphicType !== "none" ? slideData.graphicType : null;
    const legacyGraphicText = !graphicType && slideData.graphic && slideData.graphic !== "none" ? slideData.graphic : null;
    const hasGraphic = Boolean(graphicType || legacyGraphicText);
    const bulletW = hasGraphic ? 5.7 : 9.06;
    const bulletY = 1.7;
    const bulletSpacing = bullets.length <= 2 ? 1.1 : 0.9;
    bullets.forEach((bullet, i) => {
      // Accent square marker
      slide.addShape("rect", {
        x: 0.36, y: bulletY + i * bulletSpacing + 0.27, w: 0.07, h: 0.07,
        fill: { color: cfg.accentColor }, line: { color: cfg.accentColor },
      });
      slide.addText(bullet, {
        x: 0.58, y: bulletY + i * bulletSpacing, w: bulletW, h: bulletSpacing - 0.05,
        fontFace: "Lato", fontSize: 18, color: "202020", valign: "middle",
      });
    });

    // Graphic — rendered inside a solid panel per §6.5 (never floating
    // without a container). Placed to the right of the bullet column.
    if (hasGraphic) {
      const panelX = 6.3, panelY = 1.7, panelW = 3.3, panelH = 3.4;
      slide.addShape("roundRect", {
        x: panelX, y: panelY, w: panelW, h: panelH,
        rectRadius: 0.08,
        fill: { color: "F5F5F5" },
        line: { color: "E0E0E0", width: 1 },
      });
      const innerBox = { x: panelX + 0.25, y: panelY + 0.25, w: panelW - 0.5, h: panelH - 0.5 };
      if (graphicType) {
        renderGraphic(slide, graphicType, slideData.graphicData || {}, innerBox);
      } else {
        // Backward-compat: older plans only carry a free-text hint string.
        slide.addText(legacyGraphicText, {
          ...innerBox, fontFace: "Lato", fontSize: 12, color: cfg.accentColor,
          italics: true, align: "center", valign: "middle",
        });
      }
    }

    // Brand gradient bar at bottom
    addBrandGradientBar(slide, 5.43, 0.2);
  }
}

// Embed Rubik/Lato into a generated .pptx so the brand typography (§6.4)
// renders correctly even on machines without those fonts installed.
// pptxgenjs only writes the fontFace *name* into the XML — it never
// embeds the actual font binary — so this post-processes the .pptx zip
// per the OOXML "embedded fonts" spec (ECMA-376 §19.2.1.22 embeddedFontLst).
async function embedFonts(pptxPath) {
  const zip = await JSZip.loadAsync(fs.readFileSync(pptxPath));

  const contentTypesPath = "[Content_Types].xml";
  const presentationPath = "ppt/presentation.xml";
  const relsPath = "ppt/_rels/presentation.xml.rels";

  let contentTypes = await zip.file(contentTypesPath).async("string");
  let presentation = await zip.file(presentationPath).async("string");
  let rels = await zip.file(relsPath).async("string");

  // 1. Declare the .fntdata extension if not already declared.
  if (!contentTypes.includes('Extension="fntdata"')) {
    contentTypes = contentTypes.replace(
      "</Types>",
      '<Default Extension="fntdata" ContentType="application/x-fontdata"/></Types>'
    );
  }

  // 2. Add a relationship + font part for each embedded font file, and
  //    remember the rId assigned to each so presentation.xml can point to it.
  const existingIds = [...rels.matchAll(/Id="rId(\d+)"/g)].map((m) => Number(m[1]));
  let nextId = (existingIds.length ? Math.max(...existingIds) : 0) + 1;

  const withRelIds = BRAND_FONTS.map((font, i) => {
    const rId = `rId${nextId + i}`;
    const partName = `font${nextId + i}.fntdata`;
    zip.file(`ppt/fonts/${partName}`, font.buffer);
    rels = rels.replace(
      "</Relationships>",
      `<Relationship Id="${rId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font" Target="fonts/${partName}"/></Relationships>`
    );
    return { ...font, rId };
  });

  // 3. Mark the presentation as using embedded fonts, and list them —
  //    grouped by typeface, one <p:embeddedFont> per family with
  //    <p:regular>/<p:bold> children pointing at the relationship ids.
  if (!/embedTrueTypeFonts=/.test(presentation)) {
    presentation = presentation.replace(
      /<p:presentation /,
      '<p:presentation embedTrueTypeFonts="1" '
    );
  }

  const byTypeface = {};
  withRelIds.forEach((f) => {
    byTypeface[f.typeface] = byTypeface[f.typeface] || {};
    byTypeface[f.typeface][f.style] = f.rId;
  });
  const embeddedFontLst =
    "<p:embeddedFontLst>" +
    Object.entries(byTypeface)
      .map(([typeface, styles]) => {
        const children = Object.entries(styles)
          .map(([style, rId]) => `<p:${style} r:id="${rId}"/>`)
          .join("");
        return `<p:embeddedFont><p:font typeface="${typeface}"/>${children}</p:embeddedFont>`;
      })
      .join("") +
    "</p:embeddedFontLst>";

  if (/<p:notesSz\b[^/]*\/>/.test(presentation)) {
    presentation = presentation.replace(/(<p:notesSz\b[^/]*\/>)/, `$1${embeddedFontLst}`);
  } else {
    // Fallback: schema also allows it right before defaultTextStyle/extLst.
    presentation = presentation.replace("</p:presentation>", `${embeddedFontLst}</p:presentation>`);
  }

  zip.file(contentTypesPath, contentTypes);
  zip.file(presentationPath, presentation);
  zip.file(relsPath, rels);

  const outBuffer = await zip.generateAsync({ type: "nodebuffer" });
  fs.writeFileSync(pptxPath, outBuffer);
}

function slugify(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// File naming convention (manual §13): MC-[AFO]-[Unidad], e.g. "MC-MarketingDigital-U2"
function buildUnitFileName(plan) {
  const clean = (s) => (s || "").replace(/[^a-zA-Z0-9]+/g, "");
  return `MC-${clean(plan.afo) || "AFO"}-${clean(plan.unit) || "Unidad"}`;
}

// ────────────────────────────────────────────────────────────
// Serve the built React app (production only)
// ────────────────────────────────────────────────────────────
const clientBuildPath = path.join(__dirname, "..", "client", "build");
if (fs.existsSync(clientBuildPath)) {
  app.use(express.static(clientBuildPath));
  app.get("*", (req, res) => {
    res.sendFile(path.join(clientBuildPath, "index.html"));
  });
} else {
  app.get("*", (req, res) => res.status(404).json({ error: "Frontend not built. Run: npm run build inside client/" }));
}

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`Storyboard app running on :${PORT}`));
