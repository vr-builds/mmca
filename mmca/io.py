"""Reading input workbooks. Accepts a path or a file-like object (Streamlit upload)."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd

from mmca.engine import AnalysisError

SUPPORTED = (".xlsx", ".xlsm", ".xls", ".csv")


def _suffix(source: str | Path | BinaryIO, name: str | None) -> str:
    label = name or (str(source) if isinstance(source, (str, Path)) else getattr(source, "name", ""))
    return Path(label).suffix.lower()


def list_sheets(source: str | Path | BinaryIO, name: str | None = None) -> list[str]:
    ext = _suffix(source, name)
    if ext == ".csv":
        return ["(csv)"]
    if ext not in SUPPORTED:
        raise AnalysisError(f"Unsupported file type '{ext}'. Use {', '.join(SUPPORTED)}.")
    try:
        return list(pd.ExcelFile(source).sheet_names)
    except Exception as exc:  # corrupt / password-protected workbook
        raise AnalysisError(f"Could not open workbook: {exc}") from exc


def read_table(
    source: str | Path | BinaryIO, sheet: str | int = 0, name: str | None = None
) -> pd.DataFrame:
    ext = _suffix(source, name)
    if hasattr(source, "seek"):
        source.seek(0)
    try:
        if ext == ".csv":
            df = pd.read_csv(source)
        elif ext in SUPPORTED:
            df = pd.read_excel(source, sheet_name=sheet)
        else:
            raise AnalysisError(f"Unsupported file type '{ext}'. Use {', '.join(SUPPORTED)}.")
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(f"Could not read file: {exc}") from exc
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise AnalysisError("The selected sheet is empty.")
    return df
