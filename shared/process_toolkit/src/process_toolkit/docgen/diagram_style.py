"""Shared text layout helpers for generated diagrams."""

import math

from matplotlib.font_manager import FontProperties


def add_fitted_text(
    ax,
    text,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fontsize: float,
    min_fontsize: float = 5.5,
    color: str = "#1C2D43",
    fontweight: str = "normal",
    ha: str = "left",
    va: str = "center",
    linespacing: float = 1.15,
    **kwargs,
):
    """Draw text wrapped and scaled to stay inside a data-coordinate box."""
    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    origin = ax.transData.transform((x, y))
    width_px = abs(ax.transData.transform((x + width, y))[0] - origin[0])
    height_px = abs(ax.transData.transform((x, y + height))[1] - origin[1])

    fitted_lines, fitted_size = _fit_lines(
        renderer, text, width_px, height_px, fontsize, min_fontsize,
        fontweight, linespacing, kwargs.get("family"),
    )
    text_x = x + width if ha == "right" else x + width / 2 if ha == "center" else x
    return ax.text(
        text_x, y, "\n".join(fitted_lines), fontsize=fitted_size, color=color,
        fontweight=fontweight, ha=ha, va=va, linespacing=linespacing,
        clip_on=True, **kwargs,
    )


def add_fitted_figure_text(
    fig,
    text,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fontsize: float,
    min_fontsize: float = 6,
    color: str = "#1C2D43",
    fontweight: str = "normal",
    va: str = "center",
    linespacing: float = 1.15,
    **kwargs,
):
    """Draw text wrapped and scaled to stay inside a figure-fraction box."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    origin = fig.transFigure.transform((x, y))
    width_px = abs(fig.transFigure.transform((x + width, y))[0] - origin[0])
    height_px = abs(fig.transFigure.transform((x, y + height))[1] - origin[1])
    fitted_lines, fitted_size = _fit_lines(
        renderer, text, width_px, height_px, fontsize, min_fontsize,
        fontweight, linespacing, kwargs.get("family"),
    )
    return fig.text(
        x, y, "\n".join(fitted_lines), fontsize=fitted_size, color=color,
        fontweight=fontweight, va=va, linespacing=linespacing, **kwargs,
    )


def _fit_lines(
    renderer, text, width_px, height_px, fontsize, min_fontsize,
    fontweight, linespacing, family,
):
    content = str(text or "").strip()
    if not content:
        return [""], fontsize

    height_px = max(0, height_px - 6)
    chosen_lines = [content]
    chosen_size = min_fontsize
    size = fontsize
    while size >= min_fontsize:
        prop = FontProperties(size=size, weight=fontweight, family=family)
        lines = []
        for paragraph in content.splitlines() or [content]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = ""
            for word in words:
                parts = [word]
                if renderer.get_text_width_height_descent(word, prop, ismath=False)[0] > width_px:
                    parts = []
                    remainder = word
                    while remainder:
                        if renderer.get_text_width_height_descent(
                            remainder, prop, ismath=False
                        )[0] <= width_px:
                            parts.append(remainder)
                            break
                        hyphen_breaks = [
                            index + 1 for index, character in enumerate(remainder)
                            if character == "-"
                        ]
                        fitting_breaks = [
                            index for index in hyphen_breaks
                            if renderer.get_text_width_height_descent(
                                remainder[:index], prop, ismath=False
                            )[0] <= width_px
                        ]
                        if fitting_breaks:
                            split_at = fitting_breaks[-1]
                        else:
                            low, high = 1, len(remainder)
                            while low < high:
                                mid = (low + high + 1) // 2
                                if renderer.get_text_width_height_descent(
                                    remainder[:mid], prop, ismath=False
                                )[0] <= width_px:
                                    low = mid
                                else:
                                    high = mid - 1
                            split_at = low
                        parts.append(remainder[:split_at])
                        remainder = remainder[split_at:]
                for part in parts:
                    candidate = f"{current} {part}".strip()
                    if current and renderer.get_text_width_height_descent(candidate, prop, ismath=False)[0] > width_px:
                        lines.append(current)
                        current = part
                    else:
                        current = candidate
            if current:
                lines.append(current)

        _, line_height, _ = renderer.get_text_width_height_descent("Ag", prop, ismath=False)
        if len(lines) * line_height * linespacing <= height_px:
            chosen_lines, chosen_size = lines, size
            break
        chosen_lines, chosen_size = lines, size
        size = round(size - 0.5, 2)

    prop = FontProperties(size=chosen_size, weight=fontweight, family=family)
    _, line_height, _ = renderer.get_text_width_height_descent("Ag", prop, ismath=False)
    max_lines = max(1, math.floor(height_px / (line_height * linespacing)))
    if len(chosen_lines) > max_lines:
        chosen_lines = chosen_lines[:max_lines]
        last_line = chosen_lines[-1]
        ellipsis = "..."
        while last_line and renderer.get_text_width_height_descent(
            last_line + ellipsis, prop, ismath=False
        )[0] > width_px:
            last_line = last_line[:-1].rstrip()
        chosen_lines[-1] = f"{last_line}{ellipsis}"

    return chosen_lines, chosen_size


def fit_title(ax, text, x: float, y: float, width: float, *, fontsize: float = 17, **kwargs):
    """Fit a single-line title into its available banner space."""
    return add_fitted_text(
        ax, text, x, y, width, 0.42, fontsize=fontsize,
        min_fontsize=8, va="center", **kwargs,
    )
