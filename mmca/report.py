"""Excel export. One workbook per analysis, including the inputs used, so a
saved result can always be traced back to how it was produced."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd

from mmca import __version__
from mmca.engine import AnalysisResult


def _summary(r: AnalysisResult, source_name: str | None) -> pd.DataFrame:
    rows = [
        ("Source file", source_name or ""),
        ("Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        ("MMCA version", __version__),
        ("Cavity column", r.cavity_col),
        ("Measurement column", r.measurement_col),
        ("LSL", r.spec.lsl),
        ("USL", r.spec.usl),
        ("Significance level (alpha)", r.alpha),
        ("Observations used", r.n_total),
        ("Rows dropped", r.n_dropped),
        ("Cavities", len(r.cavities)),
        ("Assumptions met", "Yes" if r.assumptions_met else "No"),
        ("Capability computed", "Yes" if r.capability_computed else "No"),
        ("Capability forced despite failed assumptions", "Yes" if r.capability_forced else "No"),
        ("Pooled std dev", r.pooled_std if r.pooled_std is not None else ""),
        ("Average DPM", r.avg_dpm if r.avg_dpm is not None else ""),
        ("Equivalent overall Cpk", r.overall_cpk_equiv if r.overall_cpk_equiv is not None else ""),
    ]
    rows += [(f"Warning {i + 1}", w) for i, w in enumerate(r.warnings)]
    return pd.DataFrame(rows, columns=["Item", "Value"])


def tests_frame(r: AnalysisResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Test": t.name, "Statistic": t.statistic, "p-value": t.p_value, "Result": t.verdict}
            for t in (r.normality, r.equal_variance, r.anova)
        ]
    )


def cavity_stats_frame(r: AnalysisResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Cavity": s.cavity, "N": s.n, "Mean": s.mean, "StdDev": s.std,
             "95% CI low": s.ci95_low, "95% CI high": s.ci95_high}
            for s in r.cavity_stats
        ]
    )


def to_excel_bytes(r: AnalysisResult, source_name: str | None = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        sheets = {
            "Summary": _summary(r, source_name),
            "Tests": tests_frame(r),
            "Cavity stats": cavity_stats_frame(r),
            "ANOVA": r.anova_table,
        }
        if r.capability is not None:
            sheets["Capability"] = r.capability
        if r.tukey is not None:
            sheets["Tukey"] = r.tukey
        sheets["Residuals"] = r.residuals.assign(cavity=r.residuals["cavity"].astype(str))
        for name, frame in sheets.items():
            frame.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()
