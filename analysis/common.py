"""Chart style shared by the case-study figures."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from pipeline import config as cfg

NAVY = "#0F2C59"
TEAL = "#1F7A8C"
RUST = "#C44900"
GOLD = "#A67C2D"
GREEN = "#2E7D4F"
SLATE = "#5C6B7A"
RED = "#9B2335"
BLUE = "#3D6CB3"

MARKET_NOTE = (
    "Source: Bank of England Interactive Statistical Database. "
    "Provisional values included. Not an official Bank of England publication."
)
SYNTHETIC_NOTE = (
    "SYNTHETIC EXAMPLE — Northvale Components Ltd (fictional). "
    "Operating cash flows are simulated. SONIA and FX inputs are Bank of England data."
)


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#E6E6E6",
        "grid.linewidth": 0.8,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "font.size": 10,
        "font.family": "DejaVu Sans",
        "legend.frameon": False,
    })


def save_fig(fig, filename: str, footnote: str):
    cfg.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, 0.01, footnote, fontsize=7.5, color="#555555", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    path = cfg.FIGURE_DIR / filename
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
