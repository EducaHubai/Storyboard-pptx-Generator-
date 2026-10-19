/**
 * Output languages for the "epigrafe" flow.
 *
 * The user picks the language(s) up front. Every artifact (plan, slide text,
 * narration script, pptx, avatar voice) follows `plan.language`. A second
 * language is produced by translating the approved plan — never by
 * re-planning — so both decks share the same structure, icons and variants.
 */

const LANGUAGES = {
  en: { name: "English", cierreTitle: "Thank you", suffix: "EN" },
  es: { name: "Spanish", cierreTitle: "Gracias", suffix: "ES" },
};

function resolveLanguage(value) {
  return LANGUAGES[value] ? value : "en";
}

/** Fill the {{LANGUAGE}} / {{CIERRE_TITLE}} placeholders of a system prompt. */
function fillLanguage(prompt, lang) {
  const l = LANGUAGES[resolveLanguage(lang)];
  return prompt.replaceAll("{{LANGUAGE}}", l.name).replaceAll("{{CIERRE_TITLE}}", l.cierreTitle);
}

// Values that identify things (icons, sections, filenames…) — never translated.
const KEEP_KEYS = new Set([
  "n", "section", "variant", "icon", "format", "number", "language",
  "unit", "afo", "codigo", "epigrafe", "estimatedDuration", "contentWarning",
]);

/**
 * Take only the translatable text from `translated`, laid over the original
 * structure. The model can't change icons/variants/array lengths: anything
 * that doesn't line up with the original keeps the original value.
 */
function mergeTranslation(orig, translated, key) {
  if (typeof orig === "string") {
    if (KEEP_KEYS.has(key)) return orig;
    return typeof translated === "string" && translated.trim() ? translated : orig;
  }
  if (Array.isArray(orig)) {
    if (!Array.isArray(translated) || translated.length !== orig.length) return orig;
    return orig.map((item, i) => mergeTranslation(item, translated[i], key));
  }
  if (orig && typeof orig === "object") {
    const out = {};
    for (const k of Object.keys(orig)) {
      out[k] = mergeTranslation(orig[k], translated && typeof translated === "object" ? translated[k] : undefined, k);
    }
    return out;
  }
  return orig;
}

/** Translated copy of an approved plan, in `lang`. `translated` is the raw model JSON. */
function applyTranslation(plan, translated, lang) {
  const out = mergeTranslation(plan, translated);
  out.language = resolveLanguage(lang);
  (out.slides || []).forEach((s) => {
    if (s.section === "cierre") s.fields = { ...s.fields, title: LANGUAGES[out.language].cierreTitle };
  });
  return out;
}

module.exports = { LANGUAGES, resolveLanguage, fillLanguage, mergeTranslation, applyTranslation };
