"""Visual design of the dashboard: colour palette, Plotly theme, CSS.

Everything visual lives in this one file, so the six dashboard sections look
like one product and a colour can be changed in a single place. No database
code and no Streamlit widgets are defined here - only constants, the CSS
block, and one helper that applies the Plotly theme.
"""

from __future__ import annotations

from typing import Final

import streamlit as st
from plotly.graph_objects import Figure

# -----------------------------------------------------------------------------
# 1. COLOUR PALETTE
# -----------------------------------------------------------------------------
# A restrained dark palette: neutral greys for structure, one blue accent for
# data, and four status colours used only where a meaning is attached
# (remote / hybrid / onsite, success, warning, error).

BACKGROUND: Final[str] = "#0e1117"
SURFACE: Final[str] = "#161d29"
SURFACE_ALT: Final[str] = "#1c2431"
BORDER: Final[str] = "#232c3a"

TEXT: Final[str] = "#e6edf3"
TEXT_MUTED: Final[str] = "#8b949e"
TEXT_FAINT: Final[str] = "#6e7a8a"

ACCENT: Final[str] = "#4c8dff"
ACCENT_SOFT: Final[str] = "#2f5c94"
ACCENT_DEEP: Final[str] = "#1f3a5f"

SUCCESS: Final[str] = "#3fb950"
WARNING: Final[str] = "#d29922"
DANGER: Final[str] = "#f85149"

#: One hue, five steps. Used for single-series charts so a chart never turns
#: into a rainbow, and for ordered categories (seniority bands, top-N skills).
SEQUENTIAL: Final[list[str]] = [ACCENT_DEEP, ACCENT_SOFT, ACCENT, "#7fb0ff", "#b7d4ff"]

#: Meaningful colours only. Work-mode charts use these because remote / hybrid /
#: onsite are a genuine three-way comparison, not arbitrary categories.
WORK_MODE_COLORS: Final[dict[str, str]] = {
    "REMOTE": SUCCESS,
    "HYBRID": ACCENT,
    "ONSITE": WARNING,
    "UNKNOWN": TEXT_FAINT,
}

FONT_FAMILY: Final[str] = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif"

#: Charts are not animated: a recruiter reading a number should not wait for
#: a transition, and repeated frames make a dashboard feel unstable.
PLOTLY_CONFIG: Final[dict[str, object]] = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
    "doubleClick": False,
    "showTips": False,
}


# -----------------------------------------------------------------------------
# 2. CSS
# -----------------------------------------------------------------------------

CSS: Final[str] = """
<style>
/* ---------------------------------------------------------------- base --- */
.stApp {
    background: #0e1117;
    background-image: radial-gradient(1100px 520px at 15% -12%, #17212f 0%, #0e1117 58%);
    color: #e6edf3;
}
html, body, [class*="css"], [data-testid="stMarkdownContainer"] p {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
/* Hide the Streamlit chrome that a recruiter does not need. */
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; height: 0px; }
.block-container { padding-top: 2.4rem; padding-bottom: 3.5rem; max-width: 1480px; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* -------------------------------------------------------------- header --- */
.dash-eyebrow {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.22em;
    color: #4c8dff; text-transform: uppercase; margin-bottom: 0.5rem;
}
.dash-title {
    font-size: 2.05rem; font-weight: 750; line-height: 1.16;
    color: #e6edf3; margin: 0 0 0.45rem 0; letter-spacing: -0.02em;
}
.dash-subtitle { font-size: 0.95rem; color: #8b949e; margin: 0 0 0.2rem 0; }
.dash-rule { height: 1px; background: #232c3a; margin: 1.1rem 0 1.4rem 0; }

/* ------------------------------------------------------------ sections --- */
.section-title { font-size: 1.02rem; font-weight: 650; color: #e6edf3; margin: 0 0 0.2rem 0; }
.section-caption { font-size: 0.8rem; color: #7d8896; margin: 0 0 0.9rem 0; }

/* ------------------------------------------------------------- kpi card --- */
.kpi-card {
    background: linear-gradient(180deg, #161d29 0%, #131a24 100%);
    border: 1px solid #232c3a;
    border-left: 3px solid #4c8dff;
    border-radius: 12px;
    padding: 0.85rem 1rem 0.9rem 1rem;
    height: 100%;
}
.kpi-label {
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.11em;
    text-transform: uppercase; color: #8b949e;
}
.kpi-value {
    font-size: 1.95rem; font-weight: 700; line-height: 1.18;
    color: #e6edf3; margin-top: 0.3rem;
}
.kpi-sub { font-size: 0.74rem; color: #6e7a8a; margin-top: 0.15rem; }
.chart-empty {
    background: #131a24; border: 1px dashed #2a3341; border-radius: 10px;
    padding: 1.1rem 1.2rem; color: #8b949e; font-size: 0.85rem; margin: 0 0 0.6rem 0;
}

/* -------------------------------------------------------------- sidebar --- */
[data-testid="stSidebar"] { background: #10161f; border-right: 1px solid #1e2632; }
[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; padding-bottom: 2rem; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { font-size: 0.78rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: #8b949e; }
.sidebar-title {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.16em;
    text-transform: uppercase; color: #8b949e; margin-bottom: 0.7rem;
}
.sidebar-note { font-size: 0.72rem; color: #6e7a8a; line-height: 1.5; }
.sidebar-rule { height: 1px; background: #1e2632; margin: 1.1rem 0; }

/* ------------------------------------------------------- skill gap tab --- */
/* Hero: the target role and the match percentage, side by side. */
.gap-hero {
    display: flex; flex-wrap: wrap; align-items: stretch; gap: 1rem;
    background: linear-gradient(180deg, #161d29 0%, #131a24 100%);
    border: 1px solid #232c3a; border-left: 3px solid #4c8dff;
    border-radius: 12px; padding: 1.05rem 1.2rem 1.1rem 1.2rem;
}
.gap-hero-block { flex: 1 1 16rem; min-width: 0; }
.gap-hero-block--pct { border-left: 1px solid #232c3a; padding-left: 1.2rem; }
.gap-hero-role {
    font-size: 1.5rem; font-weight: 700; line-height: 1.2; color: #e6edf3;
    margin-top: 0.3rem; overflow-wrap: anywhere;
}
.gap-hero-pct {
    font-size: 3.1rem; font-weight: 750; line-height: 1.05; color: #4c8dff;
    margin-top: 0.2rem; letter-spacing: -0.03em;
}
.gap-hero-sub { font-size: 0.8rem; color: #8b949e; margin-top: 0.3rem; }

/* Progress bar: the share of required skills already held. */
.gap-bar {
    height: 8px; border-radius: 999px; background: #1c2431;
    border: 1px solid #232c3a; overflow: hidden; margin: 0.7rem 0 1.2rem 0;
}
.gap-bar-fill {
    height: 100%; border-radius: 999px;
    background: linear-gradient(90deg, #1f3a5f 0%, #4c8dff 100%);
}

/* Skill badges. One pill per skill, wrapping onto as many rows as needed. */
.skill-badge-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.1rem 0 0.2rem 0; }
.skill-badge {
    display: inline-block; font-size: 0.78rem; font-weight: 600; line-height: 1.35;
    padding: 0.26rem 0.62rem; border-radius: 999px;
    border: 1px solid; white-space: nowrap; overflow-wrap: anywhere;
}
.skill-badge--matched { background: rgba(63, 185, 80, 0.13);  border-color: #2c6b38; color: #6fd47e; }
.skill-badge--missing { background: rgba(210, 153, 34, 0.13); border-color: #6f5620; color: #e0b252; }
.skill-badge--extra   { background: rgba(76, 141, 255, 0.12); border-color: #2f4f80; color: #8dbaff; }
.skill-badge--unknown { background: rgba(248, 81, 73, 0.11);  border-color: #7a3230; color: #f0857e; }
.skill-empty {
    background: #131a24; border: 1px dashed #2a3341; border-radius: 10px;
    padding: 0.8rem 0.9rem; color: #8b949e; font-size: 0.82rem;
}

/* --------------------------------------------------- recommendations tab --- */
/* One card per ranked role. Matches the hero styling, so the two tabs feel
   like the same application while still being visibly different tools. */
.rec-card {
    background: linear-gradient(180deg, #161d29 0%, #131a24 100%);
    border: 1px solid #232c3a; border-left: 3px solid #4c8dff;
    border-radius: 12px; padding: 1rem 1.15rem 1.05rem 1.15rem;
    margin-bottom: 0.9rem;
}
.rec-head {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: baseline; gap: 0.6rem;
}
.rec-rank {
    font-size: 0.78rem; color: #6e7a8a; text-transform: uppercase;
    letter-spacing: 0.1em; margin-bottom: 0.15rem;
}
.rec-role {
    font-size: 1.35rem; font-weight: 700; line-height: 1.2; color: #e6edf3;
    overflow-wrap: anywhere;
}
.rec-metric { text-align: right; }
.rec-score {
    font-size: 1.7rem; font-weight: 750; color: #4c8dff;
    letter-spacing: -0.02em; line-height: 1.1;
}
.rec-score-unit { font-size: 0.9rem; color: #8b949e; font-weight: 600; }
.rec-score-label {
    font-size: 0.7rem; color: #6e7a8a; text-transform: uppercase;
    letter-spacing: 0.06em;
}
.rec-bar {
    height: 6px; border-radius: 999px; background: #1c2431;
    border: 1px solid #232c3a; overflow: hidden; margin: 0.8rem 0 0.55rem 0;
}
.rec-bar-fill {
    height: 100%; border-radius: 999px;
    background: linear-gradient(90deg, #1f3a5f 0%, #4c8dff 100%);
}
.rec-columns { display: flex; flex-wrap: wrap; gap: 1rem; }
.rec-column { flex: 1 1 16rem; min-width: 0; }
.rec-block-label {
    font-size: 0.7rem; color: #8b949e; text-transform: uppercase;
    letter-spacing: 0.06em; margin: 0.35rem 0 0.4rem 0;
}
.rec-block-note { font-size: 0.8rem; color: #6e7a8a; }
.rec-required {
    font-size: 0.8rem; color: #8b949e; line-height: 1.55; margin-top: 0.7rem;
    border-top: 1px dashed #232c3a; padding-top: 0.6rem; overflow-wrap: anywhere;
}

/* ---------------------------------------------------------------- misc --- */
[data-testid="stMetricValue"] { font-size: 1.5rem; }
[data-testid="stCaptionContainer"] { color: #6e7a8a; }
div[data-testid="stExpander"] details {
    border: 1px solid #232c3a; border-radius: 10px; background: #131a24;
}
/* Tab labels: quieter, uppercase, recruiter-friendly. */
button[data-baseweb="tab"] p { font-size: 0.82rem; font-weight: 600; color: #8b949e; }
button[data-baseweb="tab"][aria-selected="true"] p { color: #4c8dff; }
</style>
"""


# -----------------------------------------------------------------------------
# 3. FUNCTIONS
# -----------------------------------------------------------------------------


def inject_css() -> None:
    """Apply the stylesheet. Call once, right after ``st.set_page_config``."""
    st.markdown(CSS, unsafe_allow_html=True)


def apply_figure_theme(
    figure: Figure,
    *,
    height: int = 380,
    show_legend: bool = False,
) -> Figure:
    """Return ``figure`` styled for the dark dashboard, in place.

    Backgrounds stay transparent so the chart sits on the page background
    instead of inside a grey box, and the mode bar is hidden so the charts
    look finished rather than like a debug view.
    """
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, size=12, color=TEXT),
        height=height,
        margin=dict(l=8, r=18, t=18, b=8),
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.0,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hoverlabel=dict(
            bgcolor=SURFACE_ALT,
            bordercolor=BORDER,
            font=dict(family=FONT_FAMILY, size=12, color=TEXT),
        ),
        # No animation: charts should not move on rerun.
        transition=dict(duration=0),
        bargap=0.35,
    )
    figure.update_xaxes(
        gridcolor="#1e2632", zerolinecolor="#1e2632", linecolor="#1e2632",
        tickfont=dict(size=11, color=TEXT_MUTED), title_font=dict(size=12, color=TEXT_MUTED),
    )
    figure.update_yaxes(
        gridcolor="#1e2632", zerolinecolor="#1e2632", linecolor="#1e2632",
        tickfont=dict(size=11, color=TEXT_MUTED), title_font=dict(size=12, color=TEXT_MUTED),
    )
    return figure
