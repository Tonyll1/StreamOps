# Receta de PyInstaller para StreamOps.exe (la usa tools/build_exe.py).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

TOOLS = Path(SPECPATH)
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from particion import partition, stdlib_modules, top_levels  # noqa: E402

core, pack = partition()
hidden, datas, binaries = list(stdlib_modules()), [(str(ROOT / "web"), "web"), (str(TOOLS / "afinacion.json"), "tools"), (str(TOOLS / "motor.json"), "tools")], []
# Cada paquete del núcleo entra completo: así el motor descargado encuentra cualquier submódulo.
for name, dist in sorted(core.items()):
    try:
        datas += copy_metadata(dist.metadata["Name"])
    except Exception as exc:
        print("sin metadatos:", name, exc)
    for top in sorted(top_levels(dist)):
        try:
            hidden += collect_submodules(top, on_error="ignore")
            datas += collect_data_files(top)
            binaries += collect_dynamic_libs(top)
        except Exception as exc:
            print("no se pudo recoger:", top, exc)

excludes = {"torch", "torchgen", "functorch", "torchaudio", "torio", "PyInstaller", "pip", "tkinter"}
for dist in pack.values():
    excludes |= top_levels(dist)

a = Analysis(
    [str(TOOLS / "arranque.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=sorted(excludes),
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="StreamOps",
    console=False,
    upx=False,
    icon=str(TOOLS / "streamops.ico"),
)
