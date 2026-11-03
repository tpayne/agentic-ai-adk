import matplotlib.pyplot as plt

from process_toolkit.docgen.diagram_style import add_fitted_text


def test_fitted_text_wraps_long_labels_inside_the_supplied_box():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    artist = add_fitted_text(
        ax,
        "A Very Long Component Name With An UnbrokenIdentifierThatMustStillFit",
        3,
        4,
        3,
        2,
        fontsize=14,
        min_fontsize=6,
        fontweight="bold",
        ha="center",
    )
    fig.canvas.draw()

    text_bounds = artist.get_window_extent(fig.canvas.get_renderer())
    left, bottom = ax.transData.transform((3, 3))
    right, top = ax.transData.transform((6, 5))

    assert "\n" in artist.get_text()
    assert text_bounds.x0 >= left - 1
    assert text_bounds.x1 <= right + 1
    assert text_bounds.y0 >= bottom - 1
    assert text_bounds.y1 <= top + 1
    plt.close(fig)
