# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建：
    pyinstaller hanui.spec

产物：
    dist/hanui/hanui.exe          —— 双击打开 GUI
    dist/hanui/脚本名.hrpa 双击   —— 直接运行脚本
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)

# 收集所有子模块（确保动态 import 被打包）
hiddenimports = []
hiddenimports += collect_submodules("hanui")
hiddenimports += collect_submodules("playwright")

# Playwright 驱动与二进制
datas = []
datas += collect_data_files("playwright")
# 打包示例脚本
examples_dir = project_root / "examples"
if examples_dir.exists():
    for f in examples_dir.glob("*.hrpa"):
        datas.append((str(f), "examples"))

a = Analysis(
    [str(project_root / "hanui" / "launch.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型包，减小体积
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "pytest",
        "IPython",
    ],
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
    name="hanui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 无控制台窗口（双击运行用 GUI）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可放 icon.ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="hanui",
)

# macOS: 生成 .app 包
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="hanui.app",
        icon=None,
        bundle_identifier="com.hanui.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
        },
    )
