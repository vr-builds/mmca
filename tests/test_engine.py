import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_sample_data import make  # noqa: E402

from mmca.engine import (  # noqa: E402
    AnalysisError,
    SpecLimits,
    analyze,
    anderson_darling_normal,
    cp_cpk,
    cpk_equivalent_from_dpm,
    expected_dpm,
    prepare_data,
    resolve_column,
)

SPEC = SpecLimits(1.15, 1.25)


@pytest.fixture
def sample():
    return make()


# ---- spec limits -----------------------------------------------------------
def test_spec_rejects_usl_not_above_lsl():
    with pytest.raises(AnalysisError):
        SpecLimits(2.0, 1.0)


def test_spec_rejects_nan_lsl():  # the MATLAB bug: LSL was never validated
    with pytest.raises(AnalysisError):
        SpecLimits(float("nan"), 1.0)


# ---- capability maths -------------------------------------------------------
def test_cp_cpk_centred():
    cp, cpk = cp_cpk(1.20, 0.01, SPEC)
    assert cp == pytest.approx(0.1 / 0.06)
    assert cpk == pytest.approx(cp)


def test_dpm_uses_both_tails_and_real_mean():
    # Off-centre: mean 1.23, sigma 0.01 -> USL is 2 sigma away, LSL is 8 sigma away.
    below, above = expected_dpm(1.23, 0.01, SPEC)
    assert above == pytest.approx(stats.norm.sf(2) * 1e6, rel=1e-9)
    assert below < 1e-6
    # The MATLAB formula 2*(1-Phi(3*Cpk)) would double the USL tail:
    _, cpk = cp_cpk(1.23, 0.01, SPEC)
    matlab_dpm = 2 * stats.norm.sf(3 * cpk) * 1e6
    assert matlab_dpm == pytest.approx(2 * (below + above), rel=1e-6)


def test_cpk_equivalent_roundtrip_for_centred_process():
    below, above = expected_dpm(1.20, 0.01, SPEC)
    _, cpk = cp_cpk(1.20, 0.01, SPEC)
    assert cpk_equivalent_from_dpm(below + above) == pytest.approx(cpk, rel=1e-9)


def test_cpk_equivalent_zero_dpm_is_inf():
    assert math.isinf(cpk_equivalent_from_dpm(0.0))


# ---- Anderson-Darling -------------------------------------------------------
def test_ad_normal_data_passes():
    x = np.random.default_rng(1).normal(size=200)
    _, p = anderson_darling_normal(x)
    assert p > 0.05


def test_ad_skewed_data_fails():
    x = np.random.default_rng(1).exponential(size=200)
    _, p = anderson_darling_normal(x)
    assert p < 0.01


def test_ad_statistic_matches_scipy():
    x = np.random.default_rng(7).normal(size=60)
    a2s, _ = anderson_darling_normal(x)
    try:
        raw = stats.anderson(x, method="interpolate").statistic
    except TypeError:  # older SciPy without `method`
        raw = stats.anderson(x).statistic
    n = x.size
    assert a2s == pytest.approx(raw * (1 + 0.75 / n + 2.25 / n**2), rel=1e-6)


# ---- data prep ----------------------------------------------------------------
def test_prepare_drops_bad_rows_and_labels_float_cavities():
    df = pd.DataFrame({"Cav": [1.0, 2.0, None, 2.0], "Val": ["1.2", "x", "1.3", 1.25]})
    out, dropped = prepare_data(df, "Cav", "Val")
    assert dropped == 2
    assert list(out["cavity"]) == ["1", "2"]


def test_resolve_column_by_index_and_case(sample):
    assert resolve_column(sample, "2") == "Cavity"
    assert resolve_column(sample, "crimp height (mm)") == "Crimp Height (mm)"
    with pytest.raises(AnalysisError):
        resolve_column(sample, "Nope")


# ---- end to end -----------------------------------------------------------------
def test_full_analysis_on_sample(sample):
    r = analyze(sample, "Cavity", "Crimp Height (mm)", SPEC)
    assert r.cavities == ["Cav 1", "Cav 2", "Cav 3", "Cav 4"]
    assert r.normality.passed and r.equal_variance.passed
    assert not r.anova.passed and r.tukey is not None  # Cav 3 is shifted
    assert r.capability_computed
    assert len(r.capability) == 4
    # ANOVA agrees with SciPy
    groups = [sample.loc[sample.Cavity == c, "Crimp Height (mm)"] for c in r.cavities]
    assert r.anova.p_value == pytest.approx(stats.f_oneway(*groups).pvalue, rel=1e-9)
    # Residual count and zero mean per cavity
    assert len(r.residuals) == len(sample)
    assert r.residuals.groupby("cavity", observed=True)["residual"].mean().abs().max() < 1e-12


def test_capability_skipped_when_variances_differ():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "c": ["A"] * 40 + ["B"] * 40,
        "v": np.r_[rng.normal(1.2, 0.002, 40), rng.normal(1.2, 0.03, 40)],
    })
    r = analyze(df, "c", "v", SPEC)
    assert not r.equal_variance.passed
    assert not r.capability_computed and r.capability is None
    forced = analyze(df, "c", "v", SPEC, force_capability=True)
    assert forced.capability_computed and forced.capability_forced
    assert any("indicative" in w for w in forced.warnings)


def test_rejects_single_cavity():
    df = pd.DataFrame({"c": ["A"] * 10, "v": np.linspace(1, 2, 10)})
    with pytest.raises(AnalysisError, match="2 cavities"):
        analyze(df, "c", "v", SPEC)


def test_rejects_cavity_with_one_reading():
    df = pd.DataFrame({"c": ["A"] * 10 + ["B"], "v": np.linspace(1, 2, 11)})
    with pytest.raises(AnalysisError, match="Too few: B"):
        analyze(df, "c", "v", SPEC)
