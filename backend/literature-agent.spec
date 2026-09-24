from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

backend = Path(SPECPATH)
repo = backend.parent

datas = [
    (str(repo / "frontend" / "dist"), "frontend/dist"),
    (str(backend / "alembic"), "backend/alembic"),
    (str(backend / "alembic.ini"), "backend"),
] + collect_data_files("tzdata")

hiddenimports = (
    collect_submodules("literature_agent")
    + collect_submodules("alembic")
    + collect_submodules("langgraph")
    + collect_submodules("sqlalchemy")
    + collect_submodules("typesafe_sdk")
    + ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
)

a = Analysis(
    [str(backend / "run_literature_agent.py")],
    pathex=[str(backend / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiteratureAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="LiteratureAgent")
