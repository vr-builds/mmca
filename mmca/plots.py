"""Matplotlib figures — the same set the MATLAB script produced, plus spec limits.

Each function returns a Figure and never calls plt.show(), so the same code
works in Streamlit, the CLI (saved PNGs) and tests.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from scipy import stats  # noqa: E402

from mmca.engine import AnalysisResult  # noqa: E402

ACCENT = "#2563eb"
FIT = "#dc2626"
SPEC = "#6b7280"


def _style(ax) -> None:
    ax.grid(True, alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)


def _palette(n: int):
    cmap = plt.get_cmap("tab10" if n <= 10 else "tab20")
    return [cmap(i % cmap.N) for i in range(n)]


def normality(r: AnalysisResult) -> Figure:
    res = r.residuals["residual"].to_numpy()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    a1.hist(res, bins=20, density=True, color=ACCENT, alpha=0.6, edgecolor="white")
    xs = np.linspace(res.min(), res.max(), 200)
    a1.plot(xs, stats.norm.pdf(xs, res.mean(), res.std(ddof=1)), color=FIT, lw=2)
    a1.set(title="Histogram of residuals + normal fit", xlabel="Residual", ylabel="Density")
    _style(a1)
    (osm, osr), (slope, intercept, _) = stats.probplot(res, dist="norm")
    a2.scatter(osm, osr, s=12, color=ACCENT)
    a2.plot(osm, slope * np.asarray(osm) + intercept, color=FIT, lw=1.5)
    a2.set(
        title=f"Normal Q-Q plot (AD p = {r.normality.p_value:.3f})",
        xlabel="Theoretical quantiles",
        ylabel="Residual",
    )
    _style(a2)
    fig.tight_layout()
    return fig


def boxplot(r: AnalysisResult) -> Figure:
    d = r.residuals
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(r.cavities) + 3), 4.2))
    data = [d.loc[d["cavity"] == c, "value"].to_numpy() for c in r.cavities]
    ax.boxplot(data, tick_labels=r.cavities, patch_artist=True,
               boxprops=dict(facecolor="#dbeafe", edgecolor=ACCENT),
               medianprops=dict(color=FIT))
    for y, lab in ((r.spec.lsl, "LSL"), (r.spec.usl, "USL")):
        ax.axhline(y, color=SPEC, ls="--", lw=1)
        ax.annotate(lab, (1.0, y), xycoords=("axes fraction", "data"), xytext=(4, 0),
                    textcoords="offset points", va="center", color=SPEC, fontsize=8)
    ax.set(title=f"{r.measurement_col} by cavity (Levene p = {r.equal_variance.p_value:.3f})",
           xlabel="Cavity", ylabel=r.measurement_col)
    _style(ax)
    fig.tight_layout()
    return fig


def residuals_vs_order(r: AnalysisResult) -> Figure:
    d = r.residuals
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for c, col in zip(r.cavities, _palette(len(r.cavities))):
        sub = d[d["cavity"] == c]
        ax.plot(sub["obs"], sub["residual"], "o-", ms=3, lw=0.8, color=col, label=str(c))
    ax.axhline(0, color="black", lw=0.8)
    ax.set(title="Observations vs residuals", xlabel="Observation index", ylabel="Residual")
    if len(r.cavities) <= 16:
        ax.legend(title="Cavity", fontsize=8, ncol=min(8, len(r.cavities)), loc="upper right")
    _style(ax)
    fig.tight_layout()
    return fig


def means_ci(r: AnalysisResult) -> Figure:
    s = r.cavity_stats
    x = np.arange(1, len(s) + 1)
    mu = np.array([c.mean for c in s])
    err = np.array([[c.mean - c.ci95_low for c in s], [c.ci95_high - c.mean for c in s]])
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(s) + 3), 4.2))
    ax.errorbar(x, mu, yerr=err, fmt="o-", color=ACCENT, capsize=4, lw=1.2, ms=6)
    ax.set_xticks(x, [c.cavity for c in s])
    ax.set(title=f"Cavity means with 95% CI (ANOVA p = {r.anova.p_value:.3f})",
           xlabel="Cavity", ylabel=f"Mean {r.measurement_col}")
    _style(ax)
    fig.tight_layout()
    return fig


def tukey(r: AnalysisResult) -> Figure | None:
    if r.tukey is None or r.tukey.empty:
        return None
    t = r.tukey.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, max(3, 0.32 * len(t) + 1.2)))
    y = np.arange(len(t))
    colors = [FIT if sig else ACCENT for sig in t["Significant"]]
    ax.hlines(y, t["CI low"], t["CI high"], colors=colors, lw=2)
    ax.scatter(t["Mean diff (A-B)"], y, color=colors, zorder=3, s=18)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(y, [f"{a} − {b}" for a, b in zip(t["Cavity A"], t["Cavity B"])], fontsize=8)
    ax.set(title=f"Tukey-Kramer {int((1 - r.alpha) * 100)}% simultaneous CIs (red = significant)",
           xlabel="Difference in means")
    _style(ax)
    fig.tight_layout()
    return fig


def all_figures(r: AnalysisResult) -> dict[str, Figure]:
    figs = {
        "normality": normality(r),
        "boxplot": boxplot(r),
        "residuals_vs_order": residuals_vs_order(r),
        "means_ci": means_ci(r),
    }
    t = tukey(r)
    if t is not None:
        figs["tukey"] = t
    return figs
