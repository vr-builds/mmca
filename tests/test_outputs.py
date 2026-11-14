import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_sample_data import make  # noqa: E402

from mmca.cli import main  # noqa: E402
from mmca.engine import SpecLimits, analyze  # noqa: E402
from mmca.plots import all_figures  # noqa: E402
from mmca.report import to_excel_bytes  # noqa: E402


def _result():
    return analyze(make(), "Cavity", "Crimp Height (mm)", SpecLimits(1.15, 1.25))


def test_excel_report_has_expected_sheets():
    data = to_excel_bytes(_result(), "sample.xlsx")
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert {"Summary", "Tests", "Cavity stats", "ANOVA", "Capability", "Tukey", "Residuals"} <= set(sheets)
    assert len(sheets["Capability"]) == 4


def test_all_figures_render():
    figs = all_figures(_result())
    assert set(figs) == {"normality", "boxplot", "residuals_vs_order", "means_ci", "tukey"}


def test_cli_end_to_end(tmp_path):
    src = tmp_path / "data.xlsx"
    make().to_excel(src, index=False)
    code = main([str(src), "--cavity", "2", "--measurement", "Crimp Height (mm)",
                 "--lsl", "1.15", "--usl", "1.25", "--plots"])
    assert code == 0
    assert (tmp_path / "Results" / "data_capability.xlsx").exists()
    assert (tmp_path / "Results" / "data_tukey.png").exists()


def test_cli_reports_bad_column(tmp_path, capsys):
    src = tmp_path / "data.xlsx"
    make().to_excel(src, index=False)
    code = main([str(src), "--cavity", "Nope", "--measurement", "3", "--lsl", "1", "--usl", "2"])
    assert code == 2
    assert "not found" in capsys.readouterr().err
