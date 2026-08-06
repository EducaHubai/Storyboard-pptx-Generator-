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
    "search": '<circle cx="10" cy="10" r="6"/><path d="m20 20-5.2-5.2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "chat": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5V15a1.5 1.5 0 0 1-1.5 1.5H9l-5 4V5.5Z"/>',
    "chart_bar": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 20v-6M13 20v-9M18 20v-4"/>',
    "key": '<circle cx="7" cy="14" r="4"/><path d="M10 11 19 2"/><path d="M15 6l3 3M17 4l3 3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    "book": '<path d="M4 5.5S6 4 12 4s8 1.5 8 1.5v14S18 18 12 18s-8 1.5-8 1.5V5.5Z"/><path d="M12 4v14"/>',
    "briefcase": '<rect x="3" y="8" width="18" height="11" rx="1.5"/><path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15 9-2 5-5 2 2-5 5-2Z"/>',
    "link": '<path d="M9 15a4 4 0 0 1 0-6l3-3a4 4 0 0 1 6 6l-1.5 1.5"/><path d="M15 9a4 4 0 0 1 0 6l-3 3a4 4 0 0 1-6-6l1.5-1.5"/>',
    "filter": '<path d="M4 5h16l-6 8v6l-4-2v-4L4 5Z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="m4 6 8 7 8-7"/>',
    "phone": '<path d="M6 3h3l2 5-2.5 2a12 12 0 0 0 5.5 5.5l2-2.5 5 2v3a2 2 0 0 1-2 2C10.5 20.5 3.5 13.5 4 6a2 2 0 0 1 2-3Z"/>',
    "layers": '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="m4 12 8 4 8-4"/><path d="m4 16 8 4 8-4"/>',
    "money": '<circle cx="12" cy="12" r="9"/><path d="M9 9.5c0-1.2 1.3-2 3-2s3 .8 3 2-1.3 1.5-3 2-3 .8-3 2 1.3 2 3 2 3-.8 3-2"/><path d="M12 6v2M12 16v2"/>',
    "growth": '<path d="M12 21V10"/><path d="M12 10C12 5 8 3 4 3c0 5 3 8 8 8Z"/><path d="M12 13c0-4 3-6 7-6 0 4-2 7-7 7Z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2 2M16.4 16.4l2 2M5.6 18.4l2-2M16.4 7.6l2-2"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="1.5"/><path d="m16 10 5-3v10l-5-3Z"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.8-1.5A4.5 4.5 0 0 1 17.5 18H7Z"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "thumbs_up": '<path d="M7 11v9H4v-9h3Z"/><path d="M7 11l3.5-7a2 2 0 0 1 2 2v4h5a2 2 0 0 1 2 2l-1.5 6a2 2 0 0 1-2 1.5H7"/>',
    "heart": '<path d="M12 20s-7-4.5-9.3-9A5 5 0 0 1 12 6a5 5 0 0 1 9.3 5c-2.3 4.5-9.3 9-9.3 9Z"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 3H4l2-3Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "tag": '<path d="M12 3h6a2 2 0 0 1 2 2v6l-9 9-8-8 9-9Z"/><circle cx="15.5" cy="7.5" r="1.2" fill="currentColor"/>',
    "folder": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z"/>',
    "printer": '<rect x="6" y="3" width="12" height="6" rx="1"/><rect x="4" y="9" width="16" height="8" rx="1.5"/><rect x="8" y="14" width="8" height="6"/>',
    "wifi": '<path d="M2 9a15 15 0 0 1 20 0"/><path d="M5.5 13a10 10 0 0 1 13 0"/><path d="M9 17a5 5 0 0 1 6 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/>',
    "award": '<circle cx="12" cy="8" r="5"/><path d="m8.5 12.5-2 8 5.5-3 5.5 3-2-8"/>',
    "arrow_right": '<path d="M4 12h16"/><path d="m14 6 6 6-6 6"/>',
    "building": '<rect x="4" y="3" width="16" height="18"/><path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1"/>',
    "code": '<path d="m9 8-5 4 5 4"/><path d="m15 8 5 4-5 4"/>',
    "person": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6.5 7-6.5s7 2.5 7 6.5"/>',
}

ICON_NAMES = list(ICONS.keys())


def icon_svg(name, size=28, extra_style=""):
    inner = ICONS.get(name, ICONS["lightbulb"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" style="{extra_style}">{inner}</svg>'
    )
