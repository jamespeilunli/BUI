# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for BUI Windows executable

import sys
from pathlib import Path

# Get project directory
project_dir = Path(SPECPATH).parent
assets_dir = project_dir / 'assets'

block_cipher = None

# Collect all data files
datas = [
    (str(assets_dir), 'assets'),
    (str(project_dir / 'LICENSE'), '.'),
    (str(project_dir / 'THIRD_PARTY_NOTICES.md'), '.'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'imageio',
    'pyshortcuts',
    'assets_rc',  # Qt resource file
]

a = Analysis(
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(Path(SPECPATH) / 'pyi_rth_stderr.py')],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets_dir / 'bui_icon.png') if (assets_dir / 'bui_icon.png').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BUI',
)
