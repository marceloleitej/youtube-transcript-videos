"""Centralized design tokens — colors, spacing, typography.

Use these constants in new code and when refactoring old code.
Keeps the app consistent and makes theme changes single-source.
"""

# ─── Colors ─────────────────────────────────────────────────────
# Surface hierarchy (dark theme)
BG_CANVAS = "#13131f"      # app chrome
BG_SURFACE = "#1c1c2e"     # main working surface (tabs, panels)
BG_RAISED = "#242438"      # cards, inputs, inactive buttons
BG_HOVER = "#2d2d46"       # hover state for raised surfaces
BG_DEEPER = "#0a1128"      # for contrast inside panels (lists, console)

# Borders
BORDER = "#2f3056"         # subtle dividers
BORDER_FOCUS = "#3a3b66"   # slightly brighter for hover/focus

# Text
TEXT = "#f0f0f5"           # primary text
TEXT_DIM = "#9a9ab0"       # secondary text
TEXT_MUTE = "#64647d"      # tertiary / disabled / captions
TEXT_PLACEHOLDER = "#8585a0"  # higher contrast than MUTE for placeholders

# Accent / states
ACCENT = "#e94560"         # primary brand (pink/red)
ACCENT_HI = "#ff5b7a"      # hover accent
ACCENT_LO = "#b83548"      # pressed accent
SUCCESS = "#4caf50"
SUCCESS_HI = "#66bb6a"
WARN = "#f5a623"
ERROR = "#e94560"          # we reuse accent as error (no distinct red)

# ─── Spacing ────────────────────────────────────────────────────
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

# ─── Typography ─────────────────────────────────────────────────
# Font sizes (px) — 4 tier hierarchy
FONT_H1 = 22        # page titles
FONT_H2 = 16        # panel headers
FONT_BODY = 13      # default body
FONT_SMALL = 12     # dense lists, controls
FONT_CAPTION = 11   # hints, secondary info

# Weights
WEIGHT_BOLD = 700
WEIGHT_SEMI = 600
WEIGHT_REGULAR = 400

# ─── Radius ─────────────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 10


# ─── Prebuilt stylesheet fragments ──────────────────────────────

def secondary_btn_style() -> str:
    return (
        f"QPushButton {{ background-color: {BG_RAISED}; color: {TEXT}; "
        f"font-size: {FONT_BODY}px; font-weight: {WEIGHT_SEMI}; "
        f"border-radius: {RADIUS_MD - 2}px; padding: 6px 10px; }}"
        f"QPushButton:hover {{ background-color: {BG_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {BG_SURFACE}; }}"
        f"QPushButton:disabled {{ color: {TEXT_MUTE}; background-color: {BG_SURFACE}; }}"
        f"QPushButton:checked {{ background-color: {ACCENT}; color: white; }}"
    )


def primary_btn_style() -> str:
    return (
        f"QPushButton {{ background-color: {ACCENT}; color: white; "
        f"font-size: {FONT_BODY}px; font-weight: {WEIGHT_BOLD}; "
        f"border-radius: {RADIUS_MD - 2}px; padding: 8px 14px; }}"
        f"QPushButton:hover {{ background-color: {ACCENT_HI}; }}"
        f"QPushButton:pressed {{ background-color: {ACCENT_LO}; }}"
        f"QPushButton:disabled {{ background-color: {BG_RAISED}; color: {TEXT_MUTE}; }}"
    )
