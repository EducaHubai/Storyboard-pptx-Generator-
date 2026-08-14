/**
 * Structured Outputs JSON Schema for the "epigrafe" format's plan step
 * (server/system-prompt-pdf-to-plan-epigrafe.md, Mode B).
 *
 * Passed as response_format.json_schema.schema to the OpenAI Chat
 * Completions call so the API itself rejects any icon/section/variant
 * name outside what render_epigrafe/{icons,templates}.py actually support
 * — the model can no longer hallucinate an icon name that would otherwise
 * silently fall back to a generic lightbulb (icons.py's
 * `ICONS.get(name, ICONS["lightbulb"])`), which is what made GPT-generated
 * decks look visibly more generic/repetitive than the Claude Skill's.
 *
 * Must be kept in sync with server/render_epigrafe/icons.py's ICONS keys
 * and templates.py's VARIANT_RENDERERS keys.
 */

// Exact order/spelling copied from render_epigrafe/icons.py's ICONS dict.
const ICON_NAMES = [
  "lightbulb", "checklist", "database", "target", "map", "check_circle",
  "flag", "sync", "rocket", "shield", "warning", "calendar", "trending_up",
  "groups", "balance", "school", "gavel", "star", "storage", "search",
  "clock", "chat", "chart_bar", "key", "globe", "book", "briefcase",
  "compass", "link", "filter", "mail", "phone", "layers", "money", "growth",
  "settings", "video", "cloud", "lock", "thumbs_up", "heart", "eye", "bell",
  "tag", "folder", "printer", "wifi", "award", "arrow_right", "building",
  "code", "person",
];

const iconField = { type: "string", enum: ICON_NAMES };

function iconCard(extra = {}) {
  return {
    type: "object",
    properties: { icon: iconField, text: { type: "string" }, ...extra },
    required: ["icon", "text", ...Object.keys(extra)],
    additionalProperties: false,
  };
}

// ── Fixed-section field shapes ──────────────────────────────
const TITULO_FIELDS = {
  type: "object",
  properties: { title: { type: "string" } },
  required: ["title"],
  additionalProperties: false,
};

const INICIO_FIELDS = {
  type: "object",
  properties: { icon: iconField, promise: { type: "string" } },
  required: ["icon", "promise"],
  additionalProperties: false,
};

const RESUMEN_FIELDS = {
  type: "object",
  properties: {
    title: { type: "string" },
    items: { type: "array", items: iconCard() },
  },
  required: ["title", "items"],
  additionalProperties: false,
};

// Always literally "Thank you" per the format's Step 3 rule — enum-locked
// instead of just documented, so it can't drift.
const CIERRE_FIELDS = {
  type: "object",
  properties: { title: { type: "string", enum: ["Thank you"] } },
  required: ["title"],
  additionalProperties: false,
};

// ── Concepto / Puntos Clave variant field shapes ────────────
const VARIANT_FIELDS = {
  numero_hero: {
    type: "object",
    properties: {
      number: { type: "string" },
      title: { type: "string" },
      cards: { type: "array", items: iconCard() },
    },
    required: ["number", "title", "cards"],
    additionalProperties: false,
  },
  tarjeta_destacada: {
    type: "object",
    properties: {
      title: { type: "string" },
      main: {
        type: "object",
        properties: { icon: iconField, phrase: { type: "string" }, text: { type: "string" } },
        required: ["icon", "phrase", "text"],
        additionalProperties: false,
      },
      secondary: { type: "array", items: iconCard() },
    },
    required: ["title", "main", "secondary"],
    additionalProperties: false,
  },
  mito_realidad: {
    type: "object",
    properties: {
      title: { type: "string" },
      rows: {
        type: "array",
        items: {
          type: "object",
          properties: { myth: { type: "string" }, reality: { type: "string" } },
          required: ["myth", "reality"],
          additionalProperties: false,
        },
      },
    },
    required: ["title", "rows"],
    additionalProperties: false,
  },
  flujo_pasos: {
    type: "object",
    properties: {
      title: { type: "string" },
      steps: { type: "array", items: iconCard({ title: { type: "string" } }) },
    },
    required: ["title", "steps"],
    additionalProperties: false,
  },
  panel_tarjetas: {
    type: "object",
    properties: {
      icon: iconField,
      title: { type: "string" },
      cards: { type: "array", items: iconCard() },
    },
    required: ["icon", "title", "cards"],
    additionalProperties: false,
  },
};

// `enum: [value]` rather than `const` — enum is unambiguously documented as
// supported by OpenAI's strict Structured Outputs subset; const's support
// is less certain there, and this schema has no way to be live-tested
// against the real API from this environment.
function fixedSlide(section, fields) {
  return {
    type: "object",
    properties: { n: { type: "integer" }, section: { type: "string", enum: [section] }, fields },
    required: ["n", "section", "fields"],
    additionalProperties: false,
  };
}

function variantSlide(section, variant) {
  return {
    type: "object",
    properties: {
      n: { type: "integer" },
      section: { type: "string", enum: [section] },
      variant: { type: "string", enum: [variant] },
      fields: VARIANT_FIELDS[variant],
    },
    required: ["n", "section", "variant", "fields"],
    additionalProperties: false,
  };
}

const VARIANT_NAMES = Object.keys(VARIANT_FIELDS);

const SLIDE_SCHEMA = {
  anyOf: [
    fixedSlide("titulo", TITULO_FIELDS),
    fixedSlide("inicio", INICIO_FIELDS),
    fixedSlide("resumen", RESUMEN_FIELDS),
    fixedSlide("cierre", CIERRE_FIELDS),
    ...VARIANT_NAMES.map((v) => variantSlide("concepto", v)),
    ...VARIANT_NAMES.map((v) => variantSlide("puntos_clave", v)),
  ],
};

const EPIGRAFE_PLAN_SCHEMA = {
  type: "object",
  properties: {
    unit: { type: "string" },
    epigrafe: { type: "string" },
    afo: { type: "string" },
    format: { type: "string", enum: ["epigrafe"] },
    totalSlides: { type: "integer" },
    contentWarning: { type: ["string", "null"] },
    // No minItems/maxItems here on purpose: the prompt's own rule ("if the
    // épigrafe's real content can't fill 12 slides, report totalSlides
    // honestly + set contentWarning — never pad with filler") must be able
    // to produce a shorter deck; a hard schema bound would force padding.
    slides: { type: "array", items: SLIDE_SCHEMA },
  },
  required: ["unit", "epigrafe", "afo", "format", "totalSlides", "contentWarning", "slides"],
  additionalProperties: false,
};

module.exports = { EPIGRAFE_PLAN_SCHEMA, ICON_NAMES };
