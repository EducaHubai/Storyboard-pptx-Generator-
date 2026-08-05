"""Simple stroke-based line icons, 24x24 viewBox, stroke=currentColor.
Hand-authored generic shapes (not a copy of any icon library) â same set
used by the corporate-ppt Artifact tool, ported to Python.
"""

ICONS = {
    "lightbulb": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.45 1 1.2 1 2.1h5c0-.9.4-1.65 1-2.1A6 6 0 0 0 12 3Z"/>',
    "checklist": '<path d="M4 6h2m3 0h11M4 12h2m3 0h11M4 18h2m3 0h11"/><path d="m3 5 1 1 2-2m-3 7 1 1 2-2m-3 7 1 1 2-2"/>',
    "database": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>',
    "map": '<path d="M9 4 4 6v14l5-2 6 2 5-2V4l-5 2-6-2Z"/><path d="M9 4v14M15 6v14"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.5 2.5L16 9.5"/>',
    "flag": '<path d="M5 3v18"/><path d="M5 4h11l-2 4 2 4H5Z"/>',
    "sync": '<path d="M4 12a8 8 0 0 1 13.7-5.7L20 8"/><path d="M20 4v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.7L4 16"/><path d="M4 20v-4h4"/>',
    "rocket": '<path d="M12 2c2.5 2 4 5.5 4 9 0 2-1 4-1 4H9s-1-2-1-4c0-3.5 1.5-7 4-9Z"/><circle cx="12" cy="10" r="1.6"/><path d="M9 15l-2.5 2.5M15 15l2.5 2.5M10 18l-1 3M14 18l1 3"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z"/>',
    "warning": '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.9" fill="currentColor"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/>',
    "trending_up": '<path d="M4 16l6-6 4 4 6-7"/><path d="M20 7h-5v5"/>',
    "groups": '<circle cx="8.5" cy="8" r="3"/><circle cx="16" cy="9" r="2.5"/><path d="M3 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/><path d="M14.5 14.3c2.5.3 4.5 2.1 4.5 4.7"/>',
    "balance": '<path d="M12 3v17M7 21h10"/><path d="M12 6 5 8l3.2 6.5c.4.8 1.4 1.5 2.3.5.6-.7.6-1.6.3-2.3L7.5 7.7"/><path d="M12 6l7 2-3.2 6.5c-.4.8-1.4 1.5-2.3.5-.6-.7-.6-1.6-.3-2.3l3.3-5"/>',
    "school": '<path d="M12 3 2 8l10 5 10-5-10-5Z"/><path d="M6 11v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"/><path d="M22 8v6"/>',
    "gavel": '<path d="m9 7 5 5-5.5 5.5a1 1 0 0 1-1.4 0l-3.6-3.6a1 1 0 0 1 0-1.4L9 7Z"/><path d="m13 3 4 4M2 21h9"/><path d="m11 5 6 6"/>',
    "star": '<path d="m12 3 2.6 5.7 6.2.6-4.7 4.2 1.4 6.1L12 16.7 6.5 19.6l1.4-6.1-4.7-4.2 6.2-.6L12 3Z"/>',
    "storage": '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
}

ICON_NAMES = list(ICONS.keys())


def icon_svg(name, size=28, extra_style=""):
    inner = ICONS.get(name, ICONS["lightbulb"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" style="{extra_style}">{inner}</svg>'
    )
