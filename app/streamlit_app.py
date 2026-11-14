"""MMCA web UI. Run with:  streamlit run app/streamlit_app.py

The same file powers the hosted web app and the desktop build: the desktop
launcher just starts this script on localhost.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Make `mmca` importable whether run from source or from a PyInstaller bundle.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from mmca import __version__  # noqa: E402
from mmca import plots  # noqa: E402
from mmca.engine import AnalysisError, AnalysisResult, SpecLimits, TestResult, analyze  # noqa: E402
from mmca.io import list_sheets, read_table  # noqa: E402
from mmca.report import cavity_stats_frame, tests_frame, to_excel_bytes  # noqa: E402

st.set_page_config(page_title="MMCA — Capability Analysis", page_icon="📐", layout="wide")


# ---------------------------------------------------------------- helpers
@st.cache_data(show_spinner=False)
def _sheets(data: bytes, name: str) -> list[str]:
    return list_sheets(io.BytesIO(data), name)


@st.cache_data(show_spinner=False)
def _table(data: bytes, name: str, sheet: str) -> pd.DataFrame:
    return read_table(io.BytesIO(data), sheet=0 if sheet == "(csv)" else sheet, name=name)


def _guess(cols: list[str], keywords: tuple[str, ...], fallback: int) -> int:
    for i, c in enumerate(cols):
        if any(k in c.lower() for k in keywords):
            return i
    return min(fallback, len(cols) - 1)


def _show_fig(fig) -> None:
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)


def _test_card(col, t: TestResult, kind: str) -> None:
    with col:
        if kind == "assumption":
            badge = "✅ PASS" if t.passed else "❌ FAIL"
        else:
            badge = "➖ No difference" if t.passed else "⚠️ Means differ"
        st.metric(t.name, badge, f"p = {t.p_value:.4f}", delta_color="off")
        st.caption(t.verdict)


def _fmt(df: pd.DataFrame, digits: int = 4) -> pd.DataFrame:
    return df.style.format(precision=digits, na_rep="")


# ---------------------------------------------------------------- sidebar: inputs
st.sidebar.title("📐 MMCA")
st.sidebar.caption(f"Multi-cavity Measurement Capability Analysis · v{__version__}")

upload = st.sidebar.file_uploader("1 · Data file", type=["xlsx", "xlsm", "xls", "csv"])
if upload is None:
    st.title("Multi-cavity capability analysis")
    st.markdown(
        """
Upload an Excel or CSV file with **one row per measurement**. You need a
column that identifies the **cavity** and a column with the **measured value**.

The app then:
1. Checks the assumptions: residual normality (Anderson-Darling) and equal variances (Levene).
2. Compares cavity means (one-way ANOVA, with a Tukey-Kramer follow-up when they differ).
3. Computes **Cp, Cpk and expected DPM** per cavity from the pooled sigma, plus an overall equivalent Cpk.
4. Lets you download every table as an Excel report.
        """
    )
    sample = _ROOT / "sample_data" / "sample_crimp.xlsx"
    if sample.exists():
        st.download_button("Download sample data", sample.read_bytes(), "sample_crimp.xlsx")
        st.caption("Sample spec limits: LSL 1.15, USL 1.25")
    st.stop()

raw = upload.getvalue()
try:
    sheet_names = _sheets(raw, upload.name)
    sheet = (
        st.sidebar.selectbox("Sheet", sheet_names) if len(sheet_names) > 1 else sheet_names[0]
    )
    df = _table(raw, upload.name, sheet)
except AnalysisError as exc:
    st.error(str(exc))
    st.stop()

cols = list(df.columns)
if len(cols) < 2:
    st.error("The sheet needs at least two columns (cavity and measurement).")
    st.stop()

st.sidebar.markdown("**2 · Columns**")
cavity_col = st.sidebar.selectbox("Cavity column", cols, index=_guess(cols, ("cav",), 0))
meas_options = [c for c in cols if c != cavity_col]
meas_col = st.sidebar.selectbox(
    "Measurement column",
    meas_options,
    index=_guess(meas_options, ("height", "meas", "value", "width", "mm"), 0),
)

st.sidebar.markdown("**3 · Specification limits**")
c1, c2 = st.sidebar.columns(2)
lsl = c1.number_input("LSL", value=None, format="%.6g", placeholder="lower")
usl = c2.number_input("USL", value=None, format="%.6g", placeholder="upper")

with st.sidebar.expander("Advanced"):
    alpha = st.number_input("Significance level (α)", 0.001, 0.2, 0.05, 0.01, format="%.3f")
    force = st.checkbox(
        "Compute capability even if assumptions fail",
        help="The original script skips capability when normality or equal variance fails. "
        "Turn this on to see indicative numbers anyway; they'll be flagged.",
    )

run = st.sidebar.button("Run analysis", type="primary", width="stretch")

with st.expander(f"Preview: {upload.name} · {sheet} · {len(df):,} rows", expanded=False):
    st.dataframe(df.head(200), width="stretch")

# ---------------------------------------------------------------- analysis
inputs_key = (upload.name, len(raw), sheet, cavity_col, meas_col, lsl, usl, alpha, force)
if run:
    if lsl is None or usl is None:
        st.sidebar.error("Enter both LSL and USL.")
        st.stop()
    try:
        spec = SpecLimits(float(lsl), float(usl))
        with st.spinner("Analysing…"):
            st.session_state["result"] = analyze(df, cavity_col, meas_col, spec, alpha, force)
            st.session_state["result_key"] = inputs_key
    except AnalysisError as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))
        st.stop()

r: AnalysisResult | None = st.session_state.get("result")
if r is None:
    st.info("Choose the columns, enter the spec limits, then click **Run analysis**.")
    st.stop()
if st.session_state.get("result_key") != inputs_key:
    st.warning("Inputs changed since the last run. Click **Run analysis** to refresh.")

# ---------------------------------------------------------------- results
st.title(f"{r.measurement_col} by {r.cavity_col}")
st.caption(
    f"{r.n_total:,} measurements · {len(r.cavities)} cavities · "
    f"LSL {r.spec.lsl:g} · USL {r.spec.usl:g} · α = {r.alpha:g}"
)
for w in r.warnings:
    st.warning(w)

t1, t2, t3 = st.columns(3)
_test_card(t1, r.normality, "assumption")
_test_card(t2, r.equal_variance, "assumption")
_test_card(t3, r.anova, "comparison")

st.divider()
if r.capability is None:
    st.error(
        "**Capability analysis skipped:** the assumptions were not met. Investigate the "
        "charts below, or tick *Compute capability even if assumptions fail* under Advanced."
    )
else:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Equivalent overall Cpk", f"{r.overall_cpk_equiv:.3f}")
    k2.metric("Average DPM", f"{r.avg_dpm:,.1f}")
    k3.metric("Pooled std dev", f"{r.pooled_std:.4g}")
    k4.metric("Worst cavity Cpk", f"{r.capability['Cpk'].min():.3f}",
              r.capability.loc[r.capability["Cpk"].idxmin(), "Cavity"], delta_color="off")
    if r.overall_cpk_equiv >= 1.67:
        st.success("Capable process (equivalent Cpk ≥ 1.67).")
    elif r.overall_cpk_equiv >= 1.33:
        st.info("Acceptable process (1.33 ≤ equivalent Cpk < 1.67).")
    else:
        st.error("Process not capable (equivalent Cpk < 1.33).")

    st.subheader("Capability by cavity")
    st.dataframe(
        _fmt(r.capability).background_gradient(subset=["Cpk"], cmap="RdYlGn", vmin=1.0, vmax=2.0),
        width="stretch", hide_index=True,
    )
    st.caption(
        "Cp and Cpk use the pooled sigma. **Cpk (own σ)** uses each cavity's own sigma. "
        "A big gap between the two means pooling is hiding a noisy cavity. DPM counts both tails."
    )

tabs = st.tabs(["Normality", "Spread by cavity", "Residuals vs order", "Means & 95% CI",
                "Tukey-Kramer", "Tables"])
with tabs[0]:
    _show_fig(plots.normality(r))
with tabs[1]:
    _show_fig(plots.boxplot(r))
with tabs[2]:
    _show_fig(plots.residuals_vs_order(r))
    st.caption("Look for trends, steps or cycles. These suggest drift over time, which "
               "a capability index can't show on its own.")
with tabs[3]:
    _show_fig(plots.means_ci(r))
with tabs[4]:
    fig = plots.tukey(r)
    if fig is None:
        st.info("ANOVA found no significant difference between cavity means, so no post-hoc test is needed.")
    else:
        _show_fig(fig)
        st.dataframe(_fmt(r.tukey), width="stretch", hide_index=True)
with tabs[5]:
    st.markdown("**Statistical tests**")
    st.dataframe(_fmt(tests_frame(r)), width="stretch", hide_index=True)
    st.markdown("**Cavity statistics**")
    st.dataframe(_fmt(cavity_stats_frame(r)), width="stretch", hide_index=True)
    st.markdown("**ANOVA table**")
    st.dataframe(_fmt(r.anova_table), width="stretch", hide_index=True)

st.divider()
st.download_button(
    "⬇️ Download Excel report",
    to_excel_bytes(r, upload.name),
    file_name=f"{Path(upload.name).stem}_capability.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
