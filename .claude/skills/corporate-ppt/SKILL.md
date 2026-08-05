---
name: corporate-ppt
description: Generate EDUCA EDTECH Group corporate PPT decks (.pptx) for one or more epÃ­grafes of a training unit, from real source material (a PDF/document or pasted text). Produces the exact brand design system â 6 slide types, 5 layout variants, exact palette, real editable text via an HTML-first render pipeline. Use whenever the user asks to generate/create a corporate PPT or storyboard for an epÃ­grafe, references EDUCA EDTECH's PPT/storyboard format, or hands over a training unit document (temario) and wants slide decks made from it.
---

# Corporate PPT generator (EDUCA EDTECH Group)

Turns real training-unit source material into a brand-exact `.pptx`, one deck
per epÃ­grafe. Content structuring is done by you (Claude) reading the source
â no external LLM API is called; `render/render.py` only rasterizes the HTML
you generate and assembles the final file.

## Step 0 â get the source material

Accept a PDF, an already-extracted text block, or pasted content covering a
training unit. Read the whole document before doing anything else â you need
to see all the epÃ­grafes it contains, not just the first one.

## Step 1 â ask: one epÃ­grafe, or all of them?

**The same source document usually covers a whole unit with several
epÃ­grafes.** Before generating anything, identify the distinct epÃ­grafes in
the document (their titles/numbers) and ask the user explicitly:

> This document covers N epÃ­grafes: [list them]. Do you want a deck for just
> one of them, or one deck per epÃ­grafe for all of them?

Use `AskUserQuestion` with options like "Just one (pick which)" and "All N â
generate a separate deck per epÃ­grafe". If the user already named a specific
epÃ­grafe when they made the request, you can skip the question and confirm
your read of it instead ("I'll generate the deck for epÃ­grafe 3, '<title>' â
correct?").

If "all" is chosen, repeat Steps 2â5 independently **per epÃ­grafe** â each
epÃ­grafe gets its own slide count decision, its own variant choices, its own
file. Never blend content from two epÃ­grafes into one deck.

## Step 2 â extract, never invent

- Pull the real unit name, epÃ­grafe name/number, and acciÃ³n formativa/mÃ³dulo
  name from the document if present; ask the user for whichever of those
  aren't in the source.
- Every slide's content (titles, card text, steps, myths/realities) must come
  from the source material. No placeholder text, ever.
- **If the epÃ­grafe's real content can't fill 12 slides even at the minimum
  layout density, say so and ask the user how to proceed â do not pad with
  filler to hit the count.**

## Step 3 â structure (12â15 slides total)

Fixed order, six sections:

1. **TÃ­tulo** â 1 slide. Only the epÃ­grafe title. No subtitle, no module code.
2. **Inicio** â 1 slide. A welcome/promise phrase for the epÃ­grafe.
3. **Conceptos** â 3â5 slides, one core concept (or tight group) per slide.
4. **Puntos Clave** â 3â5 slides, key takeaways/steps/insights.
5. **Resumen** â 1 slide, recap grid.
6. **Cierre** â 1 slide. Only "Thank you".

The fixed slides (TÃ­tulo, Inicio, Resumen, Cierre) total 4. **Conceptos +
Puntos Clave combined must total 8â11 slides** so the deck lands in the
required 12â15 range (e.g. 4+4, 5+4, 5+5, 4+5 â not 3+3, which would put the
whole deck at 10). Size to how rich the epÃ­grafe's real content is: rich
epÃ­grafe â use the top of the range (5+5); thin epÃ­grafe â use the bottom
(4+4), and flag it per Step 2 if even that's a stretch.

Within Conceptos and within Puntos Clave: **never repeat the same layout
variant on two consecutive slides of that section.**

## Step 4 â palette (exact hex, already baked into the renderer)

| Section | Color |
|---|---|
| Conceptos | Azul oscuro `#244A80` |
| Puntos Clave | Azul medio `#2E7ABE` |
| Resumen | Burdeos `#963058` (solid bg) |
| Inicio | Teal `#60BFB8` (panel) |
| TÃ­tulo / Cierre | Full brand gradient `#60BFB8 â #2E7ABE â #244A80 â #963058 â #E96A73` |

You never write CSS/hex yourself â `render/templates.py` + `render/assets/slides.css`
already encode this exactly. You only choose section + variant + content per slide.

## Step 5 â pick a layout variant per Conceptos/Puntos Clave slide

| variant | use when | plan.json `fields` shape |
|---|---|---|
| `numero_hero` | one self-contained concept | `{number: "01", title, cards: [{icon, text}] (2-3)}` |
| `tarjeta_destacada` | one main concept + 1-2 lighter related ones | `{title, main: {icon, phrase, text}, secondary: [{icon, text}] (1-2)}` |
| `mito_realidad` | source contrasts a misconception with the correct idea | `{title, rows: [{myth, reality}] (1-3)}` |
| `flujo_pasos` | a process, sequence, or ordered steps | `{title, steps: [{icon, title, text}] (3-4)}` |
| `panel_tarjetas` | a list of tools/applications with no hierarchy or sequence between them | `{icon, title, cards: [{icon, text}] (2-4)}` |

Icon names (use exactly, only these): `lightbulb checklist database target map
check_circle flag sync rocket shield warning calendar trending_up groups
balance school gavel star storage`. Pick by real-world meaning (e.g. `gavel`
for regulatory, `groups` for people/culture, `map` for a research/discovery
step).

Fixed sections' `fields` shapes: `titulo â {title}` Â· `cierre â {title}` (default
`"Thank you"`) Â· `inicio â {icon, promise}` Â· `resumen â {title, items:
[{icon, text}] (usually 4, for the 2Ã2 grid)}`.

## Step 6 â density and avatar rules

- Max ~20 visible words per slide, max 3 ideas/bullets. Short headline
  phrases, never paragraphs.
- The HeyGen avatar overlay only appears on TÃ­tulo, Inicio, and Cierre â so
  those three can carry a little more presence; Conceptos/Puntos
  Clave/Resumen use the full canvas for content since no avatar sits there.
- No animations â this is a static deck; transitions get added later in
  HeyGen.

## Step 7 â build `plan.json` and render

Write one `plan.json` per deck (per epÃ­grafe):

```json
{
  "slides": [
    {"section": "titulo", "fields": {"title": "..."}, "notes": "[No narration â silent, ambient sound only]"},
    {"section": "inicio", "fields": {"icon": "lightbulb", "promise": "..."}, "notes": "..."},
    {"section": "concepto", "variant": "numero_hero", "fields": {...}, "notes": "..."},
    {"section": "puntos_clave", "variant": "flujo_pasos", "fields": {...}, "notes": "..."},
    {"section": "resumen", "fields": {"title": "...", "items": [...]}, "notes": "..."},
    {"section": "cierre", "fields": {"title": "Thank you"}, "notes": "[No narration â silent, ambient sound only]"}
  ]
}
```

`notes` is the spoken narration/production note for that slide (becomes the
pptx speaker notes â write it as natural spoken prose per slide, matching
what the source material actually says, never inventing claims).

Then render it:

```bash
python3 .claude/skills/corporate-ppt/render/render.py plan.json output.pptx
```

Requires `python-pptx` and `playwright` (with a Chromium binary) installed â
`pip install python-pptx playwright && playwright install chromium` if
missing. The script rasterizes each slide via headless Chromium, pulls the
real text back out as editable pptx text boxes (title/captions/steps stay
selectable and re-typeable in PowerPoint â only decorative art like the giant
hero number or card shadows is baked into the background image), and embeds
Rubik/Lato into the file so those text boxes render correctly even without
the fonts installed locally.

## Step 8 â filename and delivery

Name each file `E [cÃ³digo]-[nombre certificado]-[mÃ³dulo].pptx` per the unit's
real metadata (ask if any part is missing from the source). If the user chose
"all epÃ­grafes" in Step 1, deliver one such file per epÃ­grafe. Hand the
file(s) back to the user (e.g. via `SendUserFile`) â don't just report success
without attaching them.
