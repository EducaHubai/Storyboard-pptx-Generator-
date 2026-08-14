"""Slide template renderers — Python port of the corporate-ppt Artifact's
templates.js, producing the same markup (same slides.css) so output is
visually identical. Each function returns the full innerHTML for a
.slide-canvas element. Text meant to become a real editable pptx text box
is wrapped with class="pptx-text".
"""
import html
from icons import icon_svg

SECTION_META = {
    "concepto":     {"label": "Conceptos",    "accent": "#244A80", "tint": "rgba(36,74,128,0.08)",  "shadow": "rgba(36,74,128,0.22)"},
    "puntos_clave": {"label": "Puntos Clave", "accent": "#2E7ABE", "tint": "rgba(46,122,190,0.08)", "shadow": "rgba(46,122,190,0.22)"},
}

VARIANT_CLASS = {
    "numero_hero": "v-numero-hero",
    "tarjeta_destacada": "v-tarjeta",
    "mito_realidad": "v-mito",
    "flujo_pasos": "v-flujo",
    "panel_tarjetas": "v-panel",
}


def esc(s):
    return html.escape(s or "", quote=False)


def canvas_style_vars(meta):
    if not meta:
        return ""
    return f' style="--accent:{meta["accent"]};--accent-tint:{meta["tint"]};--accent-shadow:{meta["shadow"]};"'


def render_titulo(slide):
    return f'<div class="top-line"></div><div class="big-title pptx-text">{esc(slide["fields"].get("title"))}</div>'


def render_cierre(slide):
    title = slide["fields"].get("title") or "Thank you"
    return f'<div class="big-title pptx-text">{esc(title)}</div><div class="bottom-line"></div>'


def render_inicio(slide):
    icon = slide["fields"].get("icon", "lightbulb")
    promise = slide["fields"].get("promise", "")
    return f"""
    <div class="panel"><div class="badge">{icon_svg(icon, 110)}</div></div>
    <div class="content">
      <p class="kicker pptx-text">Inicio</p>
      <p class="promise pptx-text">{esc(promise)}</p>
    </div>
    <div class="gradient-bar"></div>"""


def render_resumen(slide):
    items = [i for i in (slide["fields"].get("items") or []) if i]
    cards = "".join(f"""
        <div class="r-card">
          <div class="badge">{icon_svg(it.get("icon"), 46)}</div>
          <p class="pptx-text">{esc(it.get("text"))}</p>
        </div>""" for it in items)
    return f"""
    <p class="kicker pptx-text">Resumen</p>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="grid count-{len(items)}">{cards}</div>"""


def render_numero_hero(slide, meta):
    cards = [c for c in (slide["fields"].get("cards") or []) if c]
    cards_html = "".join(f"""
        <div class="card">
          <div class="badge">{icon_svg(c.get("icon"), 56)}</div>
          <p class="pptx-text">{esc(c.get("text"))}</p>
        </div>""" for c in cards)
    return f"""
    <div class="glow"></div>
    <div class="accent-rail"></div>
    <div class="section-label"><div class="dot"></div><span class="pptx-text">{meta["label"]}</span></div>
    <div class="hero-number">{esc(slide["fields"].get("number") or "01")}</div>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="rule"></div>
    <div class="cards">{cards_html}</div>
    <div class="gradient-bar"></div>"""


def render_tarjeta_destacada(slide, meta):
    main = slide["fields"].get("main") or {}
    secondary = [s for s in (slide["fields"].get("secondary") or []) if s]
    sec_html = "".join(f"""
          <div class="sec-card">
            <div class="badge">{icon_svg(s.get("icon"), 30)}</div>
            <p class="pptx-text">{esc(s.get("text"))}</p>
          </div>""" for s in secondary)
    return f"""
    <div class="accent-rail"></div>
    <div class="section-label"><div class="dot"></div><span class="pptx-text">{meta["label"]}</span></div>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="row">
      <div class="main-card">
        <div class="badge">{icon_svg(main.get("icon"), 52)}</div>
        <p class="phrase pptx-text">{esc(main.get("phrase"))}</p>
        <p class="text pptx-text">{esc(main.get("text"))}</p>
      </div>
      <div class="secondary-col">{sec_html}</div>
    </div>
    <div class="gradient-bar"></div>"""


def render_mito_realidad(slide, meta):
    rows = [r for r in (slide["fields"].get("rows") or []) if r]
    rows_html = "".join(f"""
        <div class="row">
          <div class="col myth">
            <div class="badge">{icon_svg("warning", 28)}</div>
            <div><p class="lbl">MITO</p><p class="txt pptx-text">{esc(r.get("myth"))}</p></div>
          </div>
          <div class="col reality">
            <div class="badge">{icon_svg("check_circle", 28)}</div>
            <div><p class="lbl">REALIDAD</p><p class="txt pptx-text">{esc(r.get("reality"))}</p></div>
          </div>
        </div>""" for r in rows)
    return f"""
    <div class="accent-rail"></div>
    <div class="section-label"><div class="dot"></div><span class="pptx-text">{meta["label"]}</span></div>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="rows">{rows_html}</div>
    <div class="gradient-bar"></div>"""


def render_flujo_pasos(slide, meta):
    steps = [s for s in (slide["fields"].get("steps") or []) if s]
    arrow = ('<svg width="44" height="22" viewBox="0 0 48 24">'
             '<path d="M2 12 H40 M32 4 L42 12 L32 20" stroke="currentColor" stroke-width="3" '
             'fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    parts = []
    for i, s in enumerate(steps):
        if i > 0:
            parts.append(f'<div class="arrow">{arrow}</div>')
        parts.append(f"""
        <div class="step">
          <div class="num">{i + 1}</div>
          <div class="badge">{icon_svg(s.get("icon"), 48)}</div>
          <h3 class="pptx-text">{esc(s.get("title"))}</h3>
          <p class="pptx-text">{esc(s.get("text"))}</p>
        </div>""")
    return f"""
    <div class="accent-rail"></div>
    <div class="section-label"><div class="dot"></div><span class="pptx-text">{meta["label"]}</span></div>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="flow">{"".join(parts)}</div>
    <div class="gradient-bar"></div>"""


def render_panel_tarjetas(slide, meta):
    cards = [c for c in (slide["fields"].get("cards") or []) if c]
    cards_html = "".join(f"""
        <div class="stack-card">
          <div class="badge">{icon_svg(c.get("icon"), 34)}</div>
          <p class="pptx-text">{esc(c.get("text"))}</p>
        </div>""" for c in cards)
    return f"""
    <div class="side-panel"><div class="ring">{icon_svg(slide["fields"].get("icon"), 90)}</div></div>
    <div class="section-label" style="left:700px;"><div class="dot"></div><span class="pptx-text">{meta["label"]}</span></div>
    <div class="heading pptx-text">{esc(slide["fields"].get("title"))}</div>
    <div class="stack">{cards_html}</div>
    <div class="gradient-bar"></div>"""


VARIANT_RENDERERS = {
    "numero_hero": render_numero_hero,
    "tarjeta_destacada": render_tarjeta_destacada,
    "mito_realidad": render_mito_realidad,
    "flujo_pasos": render_flujo_pasos,
    "panel_tarjetas": render_panel_tarjetas,
}


def render_slide(slide):
    """Returns (css_class, style_attr, inner_html) for one slide dict:
    {section, variant, fields, notes}."""
    section = slide["section"]
    if section == "titulo":
        return "sec-titulo", "", render_titulo(slide)
    if section == "cierre":
        return "sec-cierre", "", render_cierre(slide)
    if section == "inicio":
        return "sec-inicio", "", render_inicio(slide)
    if section == "resumen":
        return "sec-resumen", "", render_resumen(slide)

    meta = SECTION_META[section]
    variant = slide.get("variant") or "numero_hero"
    renderer = VARIANT_RENDERERS[variant]
    cls = f"sec-{section} {VARIANT_CLASS[variant]} card-shadow"
    return cls, canvas_style_vars(meta), renderer(slide, meta)
