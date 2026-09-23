"""Calls OpenAI to turn one épigrafe's real source text into a plan.json,
reproducing corporate-ppt/SKILL.md's rules exactly (12-15 slides, 6 fixed
sections, 5 layout variants, the 52-icon set, density limits, never invent
content) — the same ruleset the Node app's system-prompt-*-epigrafe.md
files encode, adapted here for arbitrary source text + language instead of
a single English-only pipeline.

Uses OpenAI's Structured Outputs (response_format: json_schema, strict)
against schema.PLAN_JSON_SCHEMA, so icon/section/variant names can never
be anything the renderer doesn't support — the model literally cannot
return an invalid one. schema.validate_plan() then checks the cross-field
rules Structured Outputs can't express (slide counts, no-repeat-variant),
and a single retry is attempted with those errors fed back to the model
before giving up.

Chrome labels ("Conceptos"/"Concepts", "Resumen"/"Summary", "MITO"/"MYTH",
etc.) are field-driven, same as the corporate-ppt Skill: the model sets
`kicker`/`section_label`/`myth_label`/`reality_label` on the relevant
slides' `fields` per `language` below (render/templates.py falls back to
the Spanish chrome defaults — "Inicio", "Conceptos", "MITO", etc. — only
if a field comes back empty).
"""
from __future__ import annotations

import json
import os
import re
import time

from openai import OpenAI, RateLimitError

import schema

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
_MAX_RATE_LIMIT_RETRIES = 5
_client: OpenAI | None = None

_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


class AuthorError(Exception):
    """Raised when the model's plan.json still fails validation after one
    retry — the caller (jobs.py) catches this and marks just that task as
    'error', without failing the rest of the job."""


_SYSTEM_PROMPT_TEMPLATE = """You are an expert instructional designer at EDUCA EDTECH Group. You receive
ONE épigrafe's real source text — plus its unit/module metadata — and
return a JSON slide plan for a corporate PPT (12-15 slides) narrated by an
avatar in HeyGen.

## Rules

- Total slides: 12-15, and that is the normal outcome — any épigrafe with
  a few real paragraphs of source text holds 12-15 slides once each
  distinct point gets its own slide. Only when the source is genuinely
  tiny (a handful of sentences, with no distinct points left to give a
  slide of its own) may you go lower: then set `totalSlides` as low as
  honestly supported and set `contentWarning` explaining why. Never pad
  with filler to hit the count — but equally, never use `contentWarning`
  to hand back a short deck for an épigrafe that does have the material
  (it is rejected and sent back to you when the source is rich enough).
- Six sections in fixed order: `titulo` (1) — `inicio` (1) — `concepto`
  (3-5) — `puntos_clave` (3-5) — `resumen` (1) — `cierre` (1). Conceptos +
  Puntos Clave combined must total 8-11 slides (e.g. 4+4, 5+4, 5+5 — not
  3+3, which only reaches 10).
- Within `concepto` and within `puntos_clave`: never repeat the same
  `variant` on two consecutive slides of that section — and pick each
  variant because it's the genuine best fit for that slide's real content
  (see "use when" below), never by mechanically rotating through the list.
- Max ~20 visible words per slide, max 3 ideas/bullets. Short headline
  phrases, never paragraphs.
- Every slide's content must come from the real source text provided — no
  invented facts, no placeholder text.
- Write all slide content (titles, promise, card text, steps, myth/reality
  rows) in: {language}.
- `cierre.fields.title` is a short closing phrase equivalent to "Thank
  you", written in {language}.
- Chrome labels are per-slide fields, not auto-translated for you — set
  each one explicitly to real {language} text: `inicio.fields.kicker`
  (Spanish default "Inicio"), `resumen.fields.kicker` (Spanish default
  "Resumen"), every `concepto`/`puntos_clave` slide's
  `fields.section_label` (Spanish defaults "Conceptos"/"Puntos Clave"),
  and `mito_realidad`'s `fields.myth_label`/`fields.reality_label`
  (Spanish defaults "MITO"/"REALIDAD"). For a Spanish deck, repeat these
  Spanish defaults verbatim; for any other {language}, translate them for
  real — never leave a Spanish word sitting in an otherwise-{language}
  deck. They render in full caps either way, so write them in normal case.
- `titulo` and `inicio` never show the epígrafe's number/prefix, even if
  the source writes the title that way (e.g. source says "3. Fundamentos
  de..." — the `titulo` slide's title just says "Fundamentos de..."). The
  number is still useful elsewhere (filenames, matching scope) — it just
  never renders on a slide.

## Content QA gate (run before finalizing the JSON)

Before returning the JSON, review the full set of drafted slide content
across the whole deck — all concepto, puntos_clave, and resumen items
together, not slide-by-slide in isolation — for two failure modes. Run
this gate only once you already have a full draft that meets the 12-15
total / 8-11 combined concepto+puntos_clave targets above — its job is to
swap out weak or duplicate slides for better real content, never to
shrink the deck below those targets. Dropping a slide outright (and
therefore falling below the targets, with contentWarning) is a last
resort for when the source genuinely doesn't contain enough distinct
material to replace it — not the default response to spotting a
duplicate.

1. Duplicate or near-duplicate content. Compare each slide's core point
   against every other slide's. A concepto and a puntos_clave slide (or
   two concepto slides) that restate the same idea in different words is
   a real duplicate, not two distinct ideas. Fix it by replacing the
   weaker one with different content that's genuinely in the source —
   the épigrafe's real text almost always has more distinct material to
   draw from, so this replacement is the default fix, not merging or
   dropping. Only drop a slide (accepting a section below its 3-5 count,
   with contentWarning explaining why) if the source truly has no more
   distinct material left to replace it with.
2. Bullet-point anomalies. A slide, card, or step that is nothing but a
   bare label or short phrase with no explanatory sentence is a red
   flag, not a valid style choice. Every card/step needs the one-sentence
   "what it means / why it matters" text its fields shape already has a
   slot for (flujo_pasos's text, mito_realidad's row content,
   tarjeta_destacada's text, panel_tarjetas' card text). If a card ends
   up with only a title/icon and nothing else, either the source didn't
   actually support that card — cut it — or the supporting sentence got
   dropped while trimming to the ~20-word budget — put it back,
   tightened rather than removed.

Fix whatever these two checks surface before returning the JSON — don't
emit a plan with these problems and expect a later pass to correct it.

## Layout variants for concepto / puntos_clave — pick one per slide

| variant | use when |
|---|---|
| `numero_hero` | one self-contained concept |
| `tarjeta_destacada` | one main concept + 1-2 lighter related ones |
| `mito_realidad` | source contrasts a misconception with the correct idea |
| `flujo_pasos` | a process, sequence, or ordered steps |
| `panel_tarjetas` | a list of tools/applications, no hierarchy/sequence |

## Icons

Every icon field is restricted by the response schema to an exact set of
names — pick the closest real-world match for each slide's actual meaning
(`gavel` for regulatory/legal, `groups` for people/culture, `map` for a
research/discovery step, `rocket` for launch/scale, `shield`/`lock` for
security, `money` for cost/finance, `award` for achievement/certification)
— never default to `lightbulb` unless the slide is genuinely about an
idea/insight.

## Output

Return only the plan.json — the schema on this request already enforces
its exact shape, field names, and enums, so just fill in real content.
"""


def _build_system_prompt(language: str) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(language=language or "English")


def _build_user_message(epigrafe: dict, unit_meta: dict, previous_errors: list[str] | None) -> str:
    parts = [
        f"Unit (unidad didáctica): {unit_meta.get('unidad_nombre', '')}",
        f"Module (módulo formativo): {unit_meta.get('modulo_nombre', '')} ({unit_meta.get('modulo', '')})",
        f"Certificado (acción formativa): {unit_meta.get('certificado', '')}",
        f"Épigrafe: {epigrafe.get('codigo', '')} {epigrafe.get('titulo', '')}",
        "",
        "Real source text for this épigrafe:",
        epigrafe.get("texto", ""),
    ]
    if previous_errors:
        parts += [
            "",
            "Your previous attempt at this JSON had these problems — fix all of them:",
            *[f"- {e}" for e in previous_errors],
        ]
    return "\n".join(parts)


def _call_openai(system_prompt: str, user_message: str, model: str) -> dict:
    """Retries on 429 (TPM/RPM rate limits) — with a handful of épigrafes
    generating concurrently (jobs.py caps it at 2), it's easy to burst past
    a lower-tier org's tokens-per-minute cap even though the account isn't
    actually out of quota. OpenAI's own error message names how long to
    wait ("Please try again in 5.5s") — honor that when present, otherwise
    fall back to exponential backoff. This is orthogonal to
    generate_plan()'s validation retry below (that one re-prompts the
    model over a bad *shape*; this one just waits out a transient 429)."""
    client = _get_client()
    for attempt in range(_MAX_RATE_LIMIT_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "epigrafe_plan", "strict": True, "schema": schema.PLAN_JSON_SCHEMA},
                },
            )
            return json.loads(response.choices[0].message.content)
        except RateLimitError as e:
            if attempt == _MAX_RATE_LIMIT_RETRIES - 1:
                raise
            match = _RETRY_AFTER_RE.search(str(e))
            wait_s = float(match.group(1)) if match else 2 ** attempt
            time.sleep(wait_s + 0.5)  # small buffer past what OpenAI asked for


_MIN_SOURCE_CHARS = 200


def generate_plan(epigrafe: dict, unit_meta: dict, language: str = "English", model: str | None = None) -> dict:
    """Generates + validates one épigrafe's plan.json, retrying once with
    the validation errors fed back to the model if the first pass fails
    schema.validate_plan()'s cross-field checks. Raises AuthorError if
    both attempts fail."""
    model = model or OPENAI_MODEL
    source = (epigrafe.get("texto") or "").strip()
    if len(source) < _MIN_SOURCE_CHARS:
        # Without this the model dutifully obeys "never invent content" and
        # returns a structurally valid plan whose every text field is an
        # empty string — a deck that ships looking completely blank. Fail
        # the task instead, pointing at the real problem (extraction), and
        # leave it retryable once the parsing is fixed.
        raise AuthorError(
            f"épigrafe {epigrafe.get('codigo')} has almost no source text "
            f"({len(source)} characters) — the PDF parser couldn't extract its content, so "
            f"there's nothing to build a deck from. Check the document's structure/headings."
        )
    system_prompt = _build_system_prompt(language)

    plan = _call_openai(system_prompt, _build_user_message(epigrafe, unit_meta, None), model)
    errors = schema.validate_plan(plan, source_chars=len(source))
    if not errors:
        return plan

    retry_message = _build_user_message(epigrafe, unit_meta, errors)
    plan = _call_openai(system_prompt, retry_message, model)
    errors = schema.validate_plan(plan, source_chars=len(source))
    if errors:
        raise AuthorError(
            f"plan.json for épigrafe {epigrafe.get('codigo')} still invalid after retry: {'; '.join(errors)}"
        )
    return plan
