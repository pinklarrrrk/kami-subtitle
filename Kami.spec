# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
import sys

root = Path(SPECPATH)
src = root / "src"
vendor = src / "mic_vendor"
sys.path.insert(0, str(vendor))
model_name = "kami-asr-zh-en"
model = Path(os.environ.get("KAMI_ASR_MODEL", str(Path(os.environ["LOCALAPPDATA"]) / "MiMoReader" / model_name)))
model_files = ("tokens.txt", "encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.onnx", "joiner-epoch-99-avg-1.int8.onnx")
if not all((model / name).is_file() for name in model_files):
    raise SystemExit("Missing bilingual ASR model. Set KAMI_ASR_MODEL to the extracted model directory.")

datas = [(str(src / name), ".") for name in ("obs.html", "reader.html")]
datas += [(str(src / "fonts"), "fonts"), (str(root / "assets" / "kami.ico"), "assets"),
          *((str(model / name), model_name) for name in model_files)]
datas += collect_data_files("_sounddevice_data") + collect_data_files("tkinterdnd2")
for info in vendor.glob("*.dist-info"):
    for entry in info.rglob("*"):
        if entry.is_file() and ("license" in entry.name.lower() or "licenses" in entry.parts):
            datas.append((str(entry), str(Path("licenses") / entry.parent.relative_to(vendor))))

a = Analysis([str(src / "app.py")], pathex=[str(src), str(vendor)],
             binaries=collect_dynamic_libs("sherpa_onnx"), datas=datas,
             hiddenimports=["_cffi_backend"], excludes=["numpy", "scipy", "pandas", "PIL"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="咔咪字幕机",
          console=False, icon=str(root / "assets" / "kami.ico"), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Kami-Windows-x64", upx=False)
