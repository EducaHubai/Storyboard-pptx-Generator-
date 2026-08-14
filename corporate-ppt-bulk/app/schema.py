"""Validation + Structured Outputs JSON Schema for a single épigrafe's
plan.json, mirroring the rules in corporate-ppt/SKILL.md exactly (12-15
slides, 6 fixed sections, 5 layout variants for concepto/puntos_clave, the
52-name icon set, never-repeat-consecutive-variant).

Two things live here on purpose:
  - PLAN_JSON_SCHEMA: passed to OpenAI's response_format (json_schema,
    strict) so icon/section/variant names can never be anything the
    renderer doesn't support — see author.py.
  - validate_plan(): a second, independent check run after the API call,
    because Structured Outputs enforces *shape* (enums, required keys) but
    not *cross-field* rules like slide counts or "don't repeat the same
    variant twice in a row" — those need real validation logic, and their
    error messages are what gets fed back to the model on retry.
"""
from __future__ import annotations

ICON_NAMES = [
    "lightbulb", "checklist", "database", "target", "map", "check_circle",
    "flag", "sync", "rocket", "shield", "warning", "calendar", "trending_up",
    "groups", "balance", "school", "gavel", "star", "storage", "search",
    "clock", "chat", "chart_bar", "key", "globe", "book", "briefcase",
    "compass", "link", "filter", "mail", "phone", "layers", "money", "growth",
    "settings", "video", "cloud", "lock", "thumbs_up", "heart", "eye", "bell",
    "tag", "folder", "printer", "wifi", "award", "arrow_right", "building",
    "code", "person",
]

VARIANT_NAMES = [
    "numero_hero", "tarjeta_destacada", "mito_realidad", "flujo_pasos", "panel_tarjetas",
]

FIXED_SECTIONS = ["titulo", "inicio", "resumen", "cierre"]
VARIANT_SECTIONS = ["concepto", "puntos_clave"]
ALL_SECTIONS = FIXED_SECTIONS + VARIANT_SECTIONS

# ── Structured Outputs schema ───────────────────────────────
_ICON_FIELD = {"type": "string", "enum": ICON_NAMES}


def _icon_card(extra=None):
    props = {"icon": _ICON_FIELD, "text": {"type": "string"}}
    if extra:
        props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }


_TITULO_FIELDS = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}
_INICIO_FIELDS = {
    "type": "object",
    "properties": {"icon": _ICON_FIELD, "promise": {"type": "string"}},
    "required": ["icon", "promise"],
    "additionalProperties": False,
}
_RESUMEN_FIELDS = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "items": {"type": "array", "items": _icon_card()},
    },
    "required": ["title", "items"],
    "additionalProperties": False,
}
# No language enum-lock on cierre's title here (unlike the single-language
# Node app) — this service is multi-language (job.language), so "Thank you"
# may legitimately be "Gracias", "Merci", etc. Still: a slide, just a title.
_CIERRE_FIELDS = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}

_VARIANT_FIELDS = {
    "numero_hero": {
        "type": "object",
        "properties": {
            "number": {"type": "string"},
            "title": {"type": "string"},
            "cards": {"type": "array", "items": _icon_card()},
        },
        "required": ["number", "title", "cards"],
        "additionalProperties": False,
    },
    "tarjeta_destacada": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "main": {
                "type": "object",
                "properties": {
                    "icon": _ICON_FIELD,
                    "phrase": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["icon", "phrase", "text"],
                "additionalProperties": False,
            },
            "secondary": {"type": "array", "items": _icon_card()},
        },
        "required": ["title", "main", "secondary"],
        "additionalProperties": False,
    },
    "mito_realidad": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"myth": {"type": "string"}, "reality": {"type": "string"}},
                    "required": ["myth", "reality"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "rows"],
        "additionalProperties": False,
    },
    "flujo_pasos": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": _icon_card({"title": {"type": "string"}})},
        },
        "required": ["title", "steps"],
        "additionalProperties": False,
    },
    "panel_tarjetas": {
        "type": "object",
        "properties": {
            "icon": _ICON_FIELD,
            "title": {"type": "string"},
            "cards": {"type": "array", "items": _icon_card()},
        },
        "required": ["icon", "title", "cards"],
        "additionalProperties": False,
    },
}


def _fixed_slide(section, fields):
    return {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "section": {"type": "string", "enum": [section]},
            "fields": fields,
            "notes": {"type": "string"},
        },
        "required": ["n", "section", "fields", "notes"],
        "additionalProperties": False,
    }


def _variant_slide(section, variant):
    return {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "section": {"type": "string", "enum": [section]},
            "variant": {"type": "string", "enum": [variant]},
            "fields": _VARIANT_FIELDS[variant],
            "notes": {"type": "string"},
        },
        "required": ["n", "section", "variant", "fields", "notes"],
        "additionalProperties": False,
    }


_SLIDE_SCHEMA = {
    "anyOf": [
        _fixed_slide("titulo", _TITULO_FIELDS),
        _fixed_slide("inicio", _INICIO_FIELDS),
        _fixed_slide("resumen", _RESUMEN_FIELDS),
        _fixed_slide("cierre", _CIERRE_FIELDS),
        *[_variant_slide("concepto", v) for v in VARIANT_NAMES],
        *[_variant_slide("puntos_clave", v) for v in VARIANT_NAMES],
    ]
}

# No minItems/maxItems on the slides array on purpose: an épigrafe whose
# real content can't reach 12 slides must still be able to report a
# shorter deck with contentWarning set — never pad with filler.
PLAN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "unit": {"type": "string"},
        "epigrafe": {"type": "string"},
        "afo": {"type": "string"},
        "totalSlides": {"type": "integer"},
        "contentWarning": {"type": ["string", "null"]},
        "slides": {"type": "array", "items": _SLIDE_SCHEMA},
    },
    "required": ["unit", "epigrafe", "afo", "totalSlides", "contentWarning", "slides"],
    "additionalProperties": False,
}


# ── Cross-field validation (post-hoc, feeds the retry loop) ────
def _find_icons(fields):
    """Recursively collect every string value under any key literally
    named 'icon' inside a fields dict/list — regardless of variant shape."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "icon" and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(fields)
    return found


def validate_plan(plan: dict) -> list[str]:
    """Returns a list of human-readable error strings; empty list means
    the plan is valid. Structured Outputs already guarantees shape/enums
    when author.py uses it, so most of what's checked here is the
    cross-field rules that a per-object JSON Schema can't express."""
    errors = []

    if not isinstance(plan, dict):
        return ["plan must be a JSON object"]

    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        return ["plan.slides must be a non-empty array"]

    for i, slide in enumerate(slides):
        if not isinstance(slide, dict):
            errors.append(f"slides[{i}] is not an object")
            continue
        section = slide.get("section")
        if section not in ALL_SECTIONS:
            errors.append(f"slides[{i}].section '{section}' is not one of {ALL_SECTIONS}")
            continue
        fields = slide.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"slides[{i}] (section={section}) is missing a 'fields' object")
            fields = {}
        variant = slide.get("variant")
        if section in VARIANT_SECTIONS:
            if variant not in VARIANT_NAMES:
                errors.append(
                    f"slides[{i}] (section={section}) has variant '{variant}', "
                    f"must be one of {VARIANT_NAMES}"
                )
        elif variant is not None:
            errors.append(f"slides[{i}] (section={section}) must not set 'variant'")

        for icon in _find_icons(fields):
            if icon not in ICON_NAMES:
                errors.append(
                    f"slides[{i}] uses icon '{icon}', which is not in the allowed set — "
                    f"pick the closest real match from: {', '.join(ICON_NAMES)}"
                )

    # Section counts.
    by_section = {}
    for slide in slides:
        if isinstance(slide, dict):
            by_section.setdefault(slide.get("section"), []).append(slide)

    for fixed in FIXED_SECTIONS:
        count = len(by_section.get(fixed, []))
        if count != 1:
            errors.append(f"expected exactly 1 '{fixed}' slide, found {count}")

    n_concepto = len(by_section.get("concepto", []))
    n_puntos = len(by_section.get("puntos_clave", []))
    content_warning = plan.get("contentWarning")

    if not content_warning:
        # Full 12-15 rule only enforced when the model hasn't explicitly
        # flagged the épigrafe as too thin to reach it honestly.
        if not (3 <= n_concepto <= 5):
            errors.append(f"expected 3-5 'concepto' slides, found {n_concepto}")
        if not (3 <= n_puntos <= 5):
            errors.append(f"expected 3-5 'puntos_clave' slides, found {n_puntos}")
        if not (8 <= n_concepto + n_puntos <= 11):
            errors.append(
                f"'concepto' + 'puntos_clave' must total 8-11 slides, found {n_concepto + n_puntos}"
            )
        total = len(slides)
        if not (12 <= total <= 15):
            errors.append(f"expected 12-15 total slides, found {total} (or set contentWarning)")
    else:
        if n_concepto < 1:
            errors.append("expected at least 1 'concepto' slide even in a thin épigrafe")
        if n_puntos < 1:
            errors.append("expected at least 1 'puntos_clave' slide even in a thin épigrafe")

    # No two consecutive slides in the same variant-bearing section share a variant.
    for section in VARIANT_SECTIONS:
        section_slides = by_section.get(section, [])
        for a, b in zip(section_slides, section_slides[1:]):
            if a.get("variant") and a.get("variant") == b.get("variant"):
                errors.append(
                    f"two consecutive '{section}' slides both use variant '{a.get('variant')}' — vary them"
                )

    return errors
