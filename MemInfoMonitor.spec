# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        # ADB 번들 (있는 경우)
        # ('assets/adb/adb.exe', 'assets/adb'),
        # ('assets/adb/AdbWinApi.dll', 'assets/adb'),
    ],
    datas=[
        ('tests/fixtures/sample_meminfo.txt', 'tests/fixtures'),
        # ('assets/icons', 'assets/icons'),  # 아이콘 추가 시 활성화
    ],
    hiddenimports=[
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'plyer.platforms.win.notification',
        'winsound',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MemInfoMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icons/app.ico',  # 아이콘 추가 시 활성화
)
