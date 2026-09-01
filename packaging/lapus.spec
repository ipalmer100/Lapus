# PyInstaller spec for the Lapus desktop app.
#
# Bundles the Python backend (FastAPI/uvicorn) together with the frontend's
# production build, so the result is the whole app: no Python, no Node.js and
# no terminal on the machine that runs it. Node is needed only at BUILD time
# to produce frontend/dist; at runtime the backend serves those static files
# itself (see api/app.py's `_frontend_dist`).
#
# Produces a folder (PyInstaller "onedir"), not a single .exe. onedir starts
# instantly because nothing is extracted to a temp directory on each launch,
# and the folder itself -- copied or zipped whole -- is the "install"; the
# user still only double-clicks Lapus.exe inside it.
#
# Build from the repo root with:
#   pyinstaller packaging/lapus.spec
# (packaging/build_windows_exe.bat is the one-command wrapper; see
# packaging/README.md for prerequisites.)

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

repo_root = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is injected by PyInstaller)
backend_dir = repo_root / "backend"
frontend_dist = repo_root / "frontend" / "dist"
sections_config = repo_root / "config" / "spec_sections.json"

if not frontend_dist.is_dir():
    raise SystemExit(
        "frontend/dist not found. Run `npm install && npm run build` inside "
        "frontend/ before building the executable -- see packaging/README.md."
    )
if not sections_config.is_file():
    raise SystemExit(f"Expected the section contract at {sections_config}, not found.")

# uvicorn picks its protocol and loop implementations dynamically at runtime,
# which PyInstaller's static analysis misses -- collect them defensively
# rather than hand-picking and discovering the gap on the target machine.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("starlette")
    + ["websockets", "wsproto", "httptools", "h11", "anyio"]
)

datas = [
    (str(frontend_dist), "frontend_dist"),
    # The section contract is data, not code: catalog.py reads it from
    # sys._MEIPASS/config when frozen.
    (str(sections_config), "config"),
]

a = Analysis(
    [str(repo_root / "packaging" / "run_desktop.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Lapus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # The console is the app's status display and its off switch (see
    # desktop.py); it is not an oversight.
    console=True,
    icon=str(Path(SPECPATH) / "lapus.ico"),  # noqa: F821 - ignored on non-Windows
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Lapus",
)
