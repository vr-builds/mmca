"""Command-line interface, for batch runs and scripting.

    python -m mmca data.xlsx --cavity Cavity --measurement Height --lsl 1.10 --usl 1.30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mmca import __version__
from mmca.engine import AnalysisError, SpecLimits, analyze, resolve_column
from mmca.io import read_table


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mmca", description="Multi-cavity capability analysis")
    p.add_argument("file", type=Path, help="Excel (.xlsx/.xls) or CSV file")
    p.add_argument("--sheet", default=0, help="Sheet name or 0-based index (default: first)")
    p.add_argument("--cavity", required=True, help="Cavity column name or 1-based number")
    p.add_argument("--measurement", required=True, help="Measurement column name or 1-based number")
    p.add_argument("--lsl", type=float, required=True)
    p.add_argument("--usl", type=float, required=True)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--force", action="store_true", help="Compute capability even if assumptions fail")
    p.add_argument("--out", type=Path, help="Output folder (default: <file folder>/Results)")
    p.add_argument("--plots", action="store_true", help="Also save PNG charts")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sheet = int(args.sheet) if str(args.sheet).isdigit() else args.sheet
        df = read_table(args.file, sheet=sheet)
        cav = resolve_column(df, args.cavity)
        meas = resolve_column(df, args.measurement)
        r = analyze(df, cav, meas, SpecLimits(args.lsl, args.usl), args.alpha, args.force)
    except (AnalysisError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"\nCavity: {cav} | Measurement: {meas} | n = {r.n_total} | cavities = {len(r.cavities)}")
    print("\n--- Statistical tests ---")
    for t in (r.normality, r.equal_variance, r.anova):
        print(f"{t.name:<45} p = {t.p_value:.4f}  -> {t.verdict}")
    for w in r.warnings:
        print(f"WARNING: {w}")

    if r.capability is None:
        print("\nCapability analysis skipped: assumptions not met (use --force to override).")
    else:
        print(f"\nPooled std dev: {r.pooled_std:.6g}")
        print(r.capability.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
        print(f"\nAverage DPM: {r.avg_dpm:.2f}")
        print(f"Equivalent overall Cpk: {r.overall_cpk_equiv:.4f}")

    from mmca.report import to_excel_bytes

    out_dir = args.out or args.file.resolve().parent / "Results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.file.stem}_capability.xlsx"
    out_file.write_bytes(to_excel_bytes(r, args.file.name))
    print(f"\nSaved: {out_file}")

    if args.plots:
        from mmca.plots import all_figures

        for name, fig in all_figures(r).items():
            fig.savefig(out_dir / f"{args.file.stem}_{name}.png", dpi=150)
        print(f"Charts saved to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
