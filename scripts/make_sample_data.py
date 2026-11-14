"""Generate sample_data/sample_crimp.xlsx — 4 cavities, crimp height in mm.

Cavity 3 sits slightly high, so ANOVA flags it and the Tukey chart has
something to show.
"""

from pathlib import Path

import numpy as np
import pandas as pd


def make(seed: int = 42, n_per_cavity: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    means = {"1": 1.200, "2": 1.202, "3": 1.215, "4": 1.199}
    rows = []
    for cav, mu in means.items():
        for i, v in enumerate(rng.normal(mu, 0.012, n_per_cavity), start=1):
            rows.append({"Shot": i, "Cavity": f"Cav {cav}", "Crimp Height (mm)": round(v, 4),
                         "Operator": rng.choice(["A", "B"])})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "sample_data" / "sample_crimp.xlsx"
    out.parent.mkdir(exist_ok=True)
    make().to_excel(out, index=False, sheet_name="Crimp Data")
    print(f"Wrote {out}  (suggested spec: LSL 1.15, USL 1.25)")
