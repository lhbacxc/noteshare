# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyInstaller.building.datastruct import TOC


CONDA_ENV = Path(
    os.environ.get("NOTESHARE_CONDA_ENV")
    or os.environ.get("CONDA_PREFIX")
    or Path(sys.executable).resolve().parent
).resolve()
PINNED_DLL_NAMES = (
    "libssl-3-x64.dll",
    "libcrypto-3-x64.dll",
    "libexpat.dll",
)
PINNED_BINARY_INPUTS = []
PINNED_BINARY_TOCS = []
for dll_name in PINNED_DLL_NAMES:
    dll_path = CONDA_ENV / "Library" / "bin" / dll_name
    if dll_path.exists():
        PINNED_BINARY_INPUTS.append((str(dll_path), "."))
        PINNED_BINARY_TOCS.append((dll_name, str(dll_path), "BINARY"))

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=PINNED_BINARY_INPUTS,
    datas=[('cf_cloud.ico', '.')],
    hiddenimports=['pyexpat', 'xml.parsers.expat'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)

_pinned_names = {name.lower() for name in PINNED_DLL_NAMES}
_filtered_binaries = []
for dest_name, src_name, typecode in a.binaries:
    if os.path.basename(dest_name).lower() in _pinned_names:
        continue
    _filtered_binaries.append((dest_name, src_name, typecode))
a.binaries = TOC(_filtered_binaries + PINNED_BINARY_TOCS)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NoteShareR2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['cf_cloud.ico'],
)
