# PyInstaller spec for the MMCA desktop app.
# Build from the project root:   pyinstaller desktop/mmca.spec --noconfirm
# Output: dist/MMCA/ (Windows: MMCA.exe inside; macOS: also dist/MMCA.app)
#
# PyInstaller can only build for the OS it runs on. Windows builds come
# from the GitHub Actions workflow (.github/workflows/build.yml).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "app"), "app"),
    (str(ROOT / "mmca"), "mmca"),
    (str(ROOT / ".streamlit"), ".streamlit"),
    (str(ROOT / "sample_data"), "sample_data"),
]
datas += collect_data_files("streamlit")           # static frontend assets
datas += copy_metadata("streamlit")                 # streamlit checks its own version
for pkg in ("pandas", "numpy", "scipy", "matplotlib", "openpyxl", "altair", "pyarrow"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

hiddenimports = (
    collect_submodules("streamlit")
    + collect_submodules("mmca")
    + ["openpyxl", "xlrd", "scipy.stats", "matplotlib.backends.backend_agg"]
)

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MMCA",
    console=True,       # keep a window so users can see the URL and quit the app
    upx=False,          # UPX-packed exes trigger antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, name="MMCA", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MMCA.app",
        bundle_identifier="com.theprismpartners.mmca",
        info_plist={"CFBundleShortVersionString": "0.1.0", "NSHighResolutionCapable": True},
    )
