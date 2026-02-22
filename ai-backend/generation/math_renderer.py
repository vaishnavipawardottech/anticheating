"""
Math Renderer — LaTeX to PNG using matplotlib mathtext

Renders LaTeX math expressions to temporary PNG files that can be embedded
inline in ReportLab PDFs.  Uses matplotlib's built-in mathtext engine, so
no external LaTeX installation is required.

Supported syntax: standard matplotlib mathtext, which covers essentially
all exam-level math (fractions, integrals, summations, greek letters,
superscripts/subscripts, roots, logic symbols, etc.).

Usage:
    from generation.math_renderer import render_latex_to_png, extract_math_spans

    spans = extract_math_spans("Solve \\( x^2 + 1 = 0 \\) for x.")
    for span in spans:
        if span["type"] == "math":
            path, w, h = render_latex_to_png(span["expr"], display=span["display"])
"""

import logging
import re
import tempfile
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Lazy-import matplotlib so startup cost is paid only when math is needed.
_mpl_available: Optional[bool] = None


def _check_matplotlib() -> bool:
    global _mpl_available
    if _mpl_available is None:
        try:
            import matplotlib  # noqa: F401
            _mpl_available = True
        except ImportError:
            _mpl_available = False
            log.warning("matplotlib not installed — math rendering disabled; LaTeX will appear as plain text")
    return _mpl_available


# ─── Pattern matching ────────────────────────────────────────────────────────

# Matches \( ... \) for inline math, \[ ... \] for display math.
# We use non-greedy matching and allow newlines inside formulas.
_INLINE_PATTERN = re.compile(r'\\\((.+?)\\\)', re.DOTALL)
_DISPLAY_PATTERN = re.compile(r'\\\[(.+?)\\\]', re.DOTALL)
_COMBINED_PATTERN = re.compile(
    r'(\\\[.+?\\\]|\\\(.+?\\\))',
    re.DOTALL,
)


def has_math(text: str) -> bool:
    """Return True if text contains any LaTeX math delimiters."""
    return bool(_INLINE_PATTERN.search(text) or _DISPLAY_PATTERN.search(text))


def extract_math_spans(text: str) -> List[Dict]:
    """
    Split text into alternating plain-text and math spans.

    Returns a list of dicts:
      {"type": "text",  "content": "Solve "}
      {"type": "math",  "expr": "x^2 + 1 = 0", "display": False, "raw": "\\( x^2 + 1 = 0 \\)"}
      {"type": "text",  "content": " for x."}
    """
    if not text:
        return [{"type": "text", "content": ""}]

    spans = []
    last_end = 0

    for match in _COMBINED_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        raw = match.group(0)

        # Preceding plain text
        if start > last_end:
            spans.append({"type": "text", "content": text[last_end:start]})

        # Determine inline vs display
        is_display = raw.startswith(r'\[')
        if is_display:
            expr = raw[2:-2].strip()  # strip \[ and \]
        else:
            expr = raw[2:-2].strip()  # strip \( and \)

        spans.append({
            "type": "math",
            "expr": expr,
            "display": is_display,
            "raw": raw,
        })
        last_end = end

    # Trailing plain text
    if last_end < len(text):
        spans.append({"type": "text", "content": text[last_end:]})

    return spans if spans else [{"type": "text", "content": text}]


# ─── Rendering ───────────────────────────────────────────────────────────────

def render_latex_to_png(
    expr: str,
    fontsize: int = 11,
    display: bool = False,
    dpi: int = 150,
) -> Tuple[str, float, float]:
    """
    Render a LaTeX math expression to a temporary PNG file.

    Args:
        expr:     LaTeX expression WITHOUT outer delimiters (e.g. "x^2 + y^2")
        fontsize: Base font size in points (match the surrounding text)
        display:  True for display-mode (larger, centred), False for inline
        dpi:      Render resolution; 150 gives good PDF quality

    Returns:
        (png_path, width_pts, height_pts)
        Dimensions are in ReportLab points (1/72 inch).

    Raises:
        RuntimeError if matplotlib is not available.
        ValueError   if the expression cannot be rendered.
    """
    if not _check_matplotlib():
        raise RuntimeError("matplotlib is not installed; cannot render math")

    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.mathtext as mathtext

    # Wrap in $...$ for matplotlib mathtext
    wrapped = f"${expr}$"

    try:
        # Use a minimal figure just to capture the math text as an image
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0.0)

        effective_fontsize = fontsize + 2 if display else fontsize

        text_obj = fig.text(
            0, 0, wrapped,
            fontsize=effective_fontsize,
            color="black",
            usetex=False,  # use mathtext, not real TeX
        )

        # Compute tight bounding box
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bbox = text_obj.get_window_extent(renderer=renderer)

        # Add small padding
        pad_px = 2
        width_px = max(1, int(bbox.width) + pad_px * 2)
        height_px = max(1, int(bbox.height) + pad_px * 2)

        fig.set_size_inches(width_px / dpi, height_px / dpi)
        text_obj.set_position((pad_px / width_px, pad_px / height_px))

        fig.canvas.draw()

        # Save to a temp file (kept until process ends or caller deletes)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()

        fig.savefig(
            tmp_path,
            dpi=dpi,
            bbox_inches="tight",
            pad_inches=0.02,
            transparent=True,
            facecolor="none",
        )
        plt.close(fig)

        # Convert pixel dimensions → ReportLab points (72 pts/inch)
        width_pts = (width_px / dpi) * 72
        height_pts = (height_px / dpi) * 72

        return tmp_path, width_pts, height_pts

    except Exception as exc:
        try:
            plt.close("all")
        except Exception:
            pass
        raise ValueError(f"Failed to render LaTeX expression '{expr}': {exc}") from exc


def render_latex_to_png_safe(
    expr: str,
    fontsize: int = 11,
    display: bool = False,
    dpi: int = 150,
) -> Optional[Tuple[str, float, float]]:
    """
    Like render_latex_to_png but returns None instead of raising on failure.
    The caller should fall back to plain-text rendering.
    """
    try:
        return render_latex_to_png(expr, fontsize=fontsize, display=display, dpi=dpi)
    except Exception as exc:
        log.debug("Math render failed for '%s': %s", expr[:60], exc)
        return None
