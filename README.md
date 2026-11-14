# MMCA — Multi-cavity Measurement Capability Analysis

A Python port of the MATLAB crimp-capability script (kept in `legacy/matlab/`). It runs three ways from one codebase:

| Mode | For | How |
|---|---|---|
| **Web app** | Everyone, in a browser | `streamlit run app/streamlit_app.py`, or the Docker image |
| **Desktop app** | Users without a server: Windows `.exe` / macOS `.app` | PyInstaller via `desktop/mmca.spec` |
| **CLI** | Batch runs and scripting | `python -m mmca file.xlsx --cavity … --measurement … --lsl … --usl …` |

## Project layout

```
mmca/            stats engine (pure, no UI), Excel reader, charts, Excel report, CLI
app/             Streamlit UI
desktop/         launcher + PyInstaller spec for the desktop builds
tests/           pytest suite (engine maths, report, charts, CLI)
sample_data/     sample_crimp.xlsx (4 cavities; spec LSL 1.15, USL 1.25)
legacy/matlab/   the original script, for reference
.github/         CI: tests, then Windows + macOS desktop builds
```

## Run it in VS Code

1. Open the `MMCA` folder in VS Code and install the recommended extensions when prompted.
2. In the terminal:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   pytest -q
   ```
3. Select the `.venv` interpreter (Cmd/Ctrl+Shift+P, then **Python: Select Interpreter**).
4. Open **Run and Debug** and choose **MMCA: Web app (Streamlit)**. Your browser opens at http://localhost:8501. Upload `sample_data/sample_crimp.xlsx` and use LSL 1.15, USL 1.25.

Breakpoints work in `mmca/` and `app/`. With `runOnSave`, the app reloads when you save a file.

## Desktop builds (.exe / .app)

PyInstaller builds only for the OS it runs on.

- **Mac, local:** `pyinstaller desktop/mmca.spec --noconfirm --clean` creates `dist/MMCA.app`.
- **Windows and Mac, from CI:** push to GitHub. `.github/workflows/build.yml` runs the tests, then builds on Windows and macOS runners. Download the zips from the run's **Artifacts**. Push a tag such as `v0.1.0` to attach them to a GitHub Release.

When users open the app, a console window appears and their browser opens to the app on `127.0.0.1` only. Their data never leaves the machine.

Before wider rollout, plan for **code signing**. Unsigned apps trigger Windows SmartScreen ("Windows protected your PC") and macOS Gatekeeper. Signing needs a Windows code-signing certificate, or Azure Trusted Signing, plus an Apple Developer ID with notarization.

## Web deployment

```bash
docker build -t mmca .
docker run -p 8501:8501 mmca
```

Deploy the image to **Azure Container Apps** or **Azure App Service (Linux container)**. Streamlit has no built-in sign-in, so turn on App Service / Container Apps **built-in authentication (Microsoft Entra ID)** before exposing it. Uploaded files are processed in memory and not stored.

## Changes from the MATLAB script

| # | MATLAB behaviour | MMCA behaviour |
|---|---|---|
| 1 | DPM = `2·(1−Φ(3·Cpk))`, which counts the nearer tail twice and ignores the other | DPM = actual area below LSL + above USL, from each cavity's mean and pooled σ |
| 2 | `isscalar(USL)` checked twice; LSL never validated | Both limits validated (finite, USL > LSL) |
| 3 | A significant ANOVA printed "FAIL" | Results labelled by meaning: "Cavity means DIFFER" |
| 4 | Pooled σ only | Also shows **Cpk (own σ)** per cavity, and warns when pooling hides a noisy cavity |
| 5 | Interactive `input()` prompts | Web UI, desktop app or CLI arguments; Excel report records the inputs used |
| 6 | MATLAB `adtest` p-value (table lookup) | Anderson-Darling with the D'Agostino–Stephens adjustment (as Minitab). p-values can differ slightly from MATLAB near the 0.05 boundary |

These behaviours are unchanged: residuals per cavity, Levene on absolute deviations from the mean (MATLAB `LeveneAbsolute`), one-way ANOVA, Tukey-Kramer when ANOVA is significant, capability gated on normality + equal variance, pooled σ, equal-weight average DPM, and the overall Cpk equivalent `Φ⁻¹(1 − p/2)/3`.

**Before production use**, run both versions on 2–3 real historical files and compare the outputs. Item 1 will change DPM for any off-centre cavity, which is expected.
