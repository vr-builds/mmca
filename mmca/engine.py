"""Statistics engine for MMCA.

A Python port of the original MATLAB crimp-capability script
(legacy/matlab/crimp_capability.m), with these intentional fixes:

1. DPM per cavity is computed from both tails using the actual mean and
   sigma. The MATLAB version used 2 * (1 - Phi(3 * Cpk)), which counts the
   nearer tail twice and ignores the farther one — wrong for any
   off-centre cavity.
2. LSL is validated (the MATLAB check tested USL twice).
3. Test outcomes are labelled by what they mean. ANOVA p < alpha means
   "means differ", not "FAIL".
4. Every cavity also gets a Cpk based on its own sigma, so a cavity that
   only looks capable because of pooling is visible.

The module is pure: no I/O, no UI, no globals. Every UI (Streamlit, CLI,
desktop exe) calls `analyze()` and renders the `AnalysisResult`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_ALPHA = 0.05
MIN_PER_CAVITY = 2


class AnalysisError(ValueError):
    """Input problem the user can fix (bad column, too few rows, ...)."""


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SpecLimits:
    lsl: float
    usl: float

    def __post_init__(self) -> None:
        for name, v in (("LSL", self.lsl), ("USL", self.usl)):
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise AnalysisError(f"{name} must be a finite number (got {v!r}).")
        if self.usl <= self.lsl:
            raise AnalysisError(f"USL ({self.usl}) must be greater than LSL ({self.lsl}).")


@dataclass(frozen=True)
class TestResult:
    name: str
    statistic: float
    p_value: float
    passed: bool          # True = assumption holds / no significant difference
    verdict: str          # human-readable outcome


@dataclass(frozen=True)
class CavityStats:
    cavity: str
    n: int
    mean: float
    std: float
    ci95_low: float
    ci95_high: float


@dataclass
class AnalysisResult:
    cavity_col: str
    measurement_col: str
    spec: SpecLimits
    alpha: float
    n_total: int
    n_dropped: int
    cavities: list[str]
    cavity_stats: list[CavityStats]
    residuals: pd.DataFrame                  # columns: obs, cavity, value, residual
    normality: TestResult
    equal_variance: TestResult
    anova: TestResult
    anova_table: pd.DataFrame
    tukey: pd.DataFrame | None               # None when ANOVA not significant
    assumptions_met: bool
    capability_computed: bool
    capability_forced: bool
    pooled_std: float | None = None
    capability: pd.DataFrame | None = None
    avg_dpm: float | None = None
    overall_cpk_equiv: float | None = None
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Data preparation
# --------------------------------------------------------------------------
def _natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _cavity_label(v) -> str:
    # Excel often stores cavity IDs as floats (1.0, 2.0); show them as "1", "2".
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def resolve_column(df: pd.DataFrame, user_text: str | int) -> str:
    """Resolve a column by exact name, case-insensitive name, or 1-based index."""
    cols = [str(c) for c in df.columns]
    text = str(user_text).strip()
    if text in cols:
        return text
    if text.isdigit() and 1 <= int(text) <= len(cols):
        return cols[int(text) - 1]
    lowered = {c.lower(): c for c in cols}
    if text.lower() in lowered:
        return lowered[text.lower()]
    raise AnalysisError(f'Column "{text}" not found. Available: {", ".join(cols)}')


def prepare_data(df: pd.DataFrame, cavity_col: str, measurement_col: str) -> tuple[pd.DataFrame, int]:
    """Return a clean frame with `cavity` (str) and `value` (float) columns, plus rows dropped."""
    df = df.rename(columns=lambda c: str(c))
    for c in (cavity_col, measurement_col):
        if c not in df.columns:
            raise AnalysisError(f'Column "{c}" not found.')
    if cavity_col == measurement_col:
        raise AnalysisError("Cavity and measurement must be different columns.")

    out = pd.DataFrame(
        {
            "cavity": df[cavity_col],
            "value": pd.to_numeric(df[measurement_col], errors="coerce"),
        }
    )
    before = len(out)
    out = out[out["cavity"].notna() & np.isfinite(out["value"])].copy()
    out["cavity"] = out["cavity"].map(_cavity_label)
    out = out[out["cavity"] != ""]
    dropped = before - len(out)

    if out.empty:
        raise AnalysisError(
            f'No usable rows: "{measurement_col}" has no numeric values alongside a cavity.'
        )
    return out.reset_index(drop=True), dropped


# --------------------------------------------------------------------------
# Statistical tests
# --------------------------------------------------------------------------
def anderson_darling_normal(x: np.ndarray) -> tuple[float, float]:
    """Anderson-Darling test for normality, mean and sigma estimated from data.

    Returns (A2*, p) using the D'Agostino & Stephens (1986) small-sample
    adjustment and p-value approximation — the same method Minitab reports.
    Implemented directly so the result doesn't depend on SciPy's changing
    `anderson()` API.
    """
    x = np.sort(np.asarray(x, dtype=float))
    n = x.size
    if n < 8:
        raise AnalysisError(f"Normality test needs at least 8 observations (got {n}).")
    s = x.std(ddof=1)
    if s == 0:
        raise AnalysisError("All measurements are identical; normality cannot be tested.")
    z = (x - x.mean()) / s
    logcdf = stats.norm.logcdf(z)
    logsf = stats.norm.logsf(z)
    i = np.arange(1, n + 1)
    a2 = -n - np.mean((2 * i - 1) * (logcdf + logsf[::-1]))
    a2s = a2 * (1 + 0.75 / n + 2.25 / n**2)

    if a2s >= 0.6:
        p = math.exp(1.2937 - 5.709 * a2s + 0.0186 * a2s**2)
    elif a2s >= 0.34:
        p = math.exp(0.9177 - 4.279 * a2s - 1.38 * a2s**2)
    elif a2s >= 0.2:
        p = 1 - math.exp(-8.318 + 42.796 * a2s - 59.938 * a2s**2)
    else:
        p = 1 - math.exp(-13.436 + 101.14 * a2s - 223.73 * a2s**2)
    return float(a2s), float(min(max(p, 0.0), 1.0))


def _anova_table(groups: list[np.ndarray]) -> tuple[pd.DataFrame, float, float]:
    allv = np.concatenate(groups)
    grand = allv.mean()
    k, n = len(groups), allv.size
    ss_between = sum(g.size * (g.mean() - grand) ** 2 for g in groups)
    ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
    df_b, df_w = k - 1, n - k
    ms_b, ms_w = ss_between / df_b, ss_within / df_w
    f = ms_b / ms_w if ms_w > 0 else math.inf
    p = float(stats.f.sf(f, df_b, df_w)) if math.isfinite(f) else 0.0
    table = pd.DataFrame(
        {
            "Source": ["Cavity", "Error", "Total"],
            "SS": [ss_between, ss_within, ss_between + ss_within],
            "df": [df_b, df_w, n - 1],
            "MS": [ms_b, ms_w, np.nan],
            "F": [f, np.nan, np.nan],
            "p": [p, np.nan, np.nan],
        }
    )
    return table, float(f), p


def _tukey(groups: list[np.ndarray], labels: list[str], alpha: float) -> pd.DataFrame:
    res = stats.tukey_hsd(*groups)  # Tukey-Kramer for unequal n
    ci = res.confidence_interval(confidence_level=1 - alpha)
    rows = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            rows.append(
                {
                    "Cavity A": labels[i],
                    "Cavity B": labels[j],
                    "Mean diff (A-B)": res.statistic[i, j],
                    "CI low": ci.low[i, j],
                    "CI high": ci.high[i, j],
                    "p (adj)": res.pvalue[i, j],
                    "Significant": bool(res.pvalue[i, j] < alpha),
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Capability
# --------------------------------------------------------------------------
def cp_cpk(mu: float, sigma: float, spec: SpecLimits) -> tuple[float, float]:
    if sigma <= 0:
        return math.inf, math.inf
    cp = (spec.usl - spec.lsl) / (6 * sigma)
    cpk = min((spec.usl - mu) / (3 * sigma), (mu - spec.lsl) / (3 * sigma))
    return cp, cpk


def expected_dpm(mu: float, sigma: float, spec: SpecLimits) -> tuple[float, float]:
    """Expected defects per million below LSL and above USL (normal model)."""
    if sigma <= 0:
        below = 1e6 if mu < spec.lsl else 0.0
        above = 1e6 if mu > spec.usl else 0.0
        return below, above
    below = stats.norm.cdf((spec.lsl - mu) / sigma) * 1e6
    above = stats.norm.sf((spec.usl - mu) / sigma) * 1e6
    return float(below), float(above)


def cpk_equivalent_from_dpm(dpm: float) -> float:
    """Cpk of a centred process with the same total defect rate.

    Same convention as the MATLAB script: z = Phi^-1(1 - p/2), Cpk = z/3.
    """
    p = dpm / 1e6
    if p <= 0:
        return math.inf
    if p >= 1:
        return -math.inf
    return float(stats.norm.isf(p / 2) / 3)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def analyze(
    df: pd.DataFrame,
    cavity_col: str,
    measurement_col: str,
    spec: SpecLimits,
    alpha: float = DEFAULT_ALPHA,
    force_capability: bool = False,
) -> AnalysisResult:
    if not 0 < alpha < 0.5:
        raise AnalysisError("Significance level must be between 0 and 0.5.")

    data, dropped = prepare_data(df, cavity_col, measurement_col)
    cavities = sorted(data["cavity"].unique(), key=_natural_key)
    if len(cavities) < 2:
        raise AnalysisError("At least 2 cavities are needed to compare cavities.")

    groups = [data.loc[data["cavity"] == c, "value"].to_numpy() for c in cavities]
    small = [c for c, g in zip(cavities, groups) if g.size < MIN_PER_CAVITY]
    if small:
        raise AnalysisError(
            f"Each cavity needs at least {MIN_PER_CAVITY} measurements. Too few: {', '.join(small)}"
        )

    warnings: list[str] = []
    if dropped:
        warnings.append(f"{dropped} row(s) dropped (missing cavity or non-numeric measurement).")

    # Per-cavity statistics and residuals (residual = value - cavity mean)
    cav_stats: list[CavityStats] = []
    for c, g in zip(cavities, groups):
        n, mu, sd = g.size, float(g.mean()), float(g.std(ddof=1))
        half = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
        cav_stats.append(CavityStats(c, n, mu, sd, mu - half, mu + half))

    means = {s.cavity: s.mean for s in cav_stats}
    resid = data.assign(residual=data["value"] - data["cavity"].map(means))
    resid["cavity"] = pd.Categorical(resid["cavity"], categories=cavities, ordered=True)
    resid = resid.sort_values("cavity", kind="stable").reset_index(drop=True)
    resid.insert(0, "obs", np.arange(1, len(resid) + 1))

    # Assumption tests
    a2, p_ad = anderson_darling_normal(resid["residual"].to_numpy())
    normality = TestResult(
        "Anderson-Darling normality (residuals)", a2, p_ad, p_ad > alpha,
        "Residuals consistent with normal" if p_ad > alpha else "Residuals NOT normal",
    )
    if all(np.ptp(g) == 0 for g in groups):
        raise AnalysisError("Every cavity has zero variation; variance tests are undefined.")
    lev_stat, p_lev = stats.levene(*groups, center="mean")  # = MATLAB 'LeveneAbsolute'
    equal_variance = TestResult(
        "Levene equal variance (absolute deviations)", float(lev_stat), float(p_lev), p_lev > alpha,
        "Variances consistent across cavities" if p_lev > alpha else "Variances DIFFER across cavities",
    )

    # Means comparison
    anova_table, f, p_anova = _anova_table(groups)
    anova = TestResult(
        "One-way ANOVA (cavity means)", f, p_anova, p_anova > alpha,
        "No significant difference in means" if p_anova > alpha else "Cavity means DIFFER",
    )
    tukey = _tukey(groups, cavities, alpha) if p_anova < alpha else None

    assumptions_met = normality.passed and equal_variance.passed
    result = AnalysisResult(
        cavity_col=cavity_col,
        measurement_col=measurement_col,
        spec=spec,
        alpha=alpha,
        n_total=len(data),
        n_dropped=dropped,
        cavities=cavities,
        cavity_stats=cav_stats,
        residuals=resid,
        normality=normality,
        equal_variance=equal_variance,
        anova=anova,
        anova_table=anova_table,
        tukey=tukey,
        assumptions_met=assumptions_met,
        capability_computed=False,
        capability_forced=False,
        warnings=warnings,
    )

    if not assumptions_met and not force_capability:
        return result
    if not assumptions_met:
        result.capability_forced = True
        warnings.append(
            "Capability computed although assumptions failed. Treat Cp/Cpk/DPM as indicative only."
        )

    # Pooled sigma (weighted by degrees of freedom), as in the MATLAB script
    num = sum((s.n - 1) * s.std**2 for s in cav_stats)
    den = sum(s.n - 1 for s in cav_stats)
    pooled = math.sqrt(num / den)

    rows = []
    for s in cav_stats:
        cp, cpk = cp_cpk(s.mean, pooled, spec)
        below, above = expected_dpm(s.mean, pooled, spec)
        _, cpk_own = cp_cpk(s.mean, s.std, spec)
        rows.append(
            {
                "Cavity": s.cavity,
                "N": s.n,
                "Mean": s.mean,
                "StdDev (own)": s.std,
                "Cp": cp,
                "Cpk": cpk,
                "Cpk (own σ)": cpk_own,
                "DPM < LSL": below,
                "DPM > USL": above,
                "DPM": below + above,
            }
        )
    cap = pd.DataFrame(rows)
    # Equal weighting per cavity, as in MATLAB — assumes each cavity
    # produces the same volume (true for a multi-cavity tool per shot).
    avg_dpm = float(cap["DPM"].mean())

    result.capability_computed = True
    result.pooled_std = pooled
    result.capability = cap
    result.avg_dpm = avg_dpm
    result.overall_cpk_equiv = cpk_equivalent_from_dpm(avg_dpm)

    worst = cap.loc[cap["Cpk (own σ)"].idxmin()]
    if worst["Cpk (own σ)"] < worst["Cpk"] - 0.2:
        warnings.append(
            f"Cavity {worst['Cavity']}: Cpk with its own sigma ({worst['Cpk (own σ)']:.2f}) is well "
            f"below the pooled Cpk ({worst['Cpk']:.2f}). Pooling may be hiding a problem."
        )
    return result
