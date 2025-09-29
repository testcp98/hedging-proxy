# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['coin.py'],
    pathex=[],
    binaries=[
        ('/Users/chenp/code/coin/.venv/lib/python3.12/site-packages/lighter/signers/signer-arm64.dylib', 'lighter/signers/'),
        ('/Users/chenp/code/coin/.venv/lib/python3.12/site-packages/lighter/signers/signer-amd64.so', 'lighter/signers/'),
    ],
    datas=[],
    hiddenimports=['lighter', 'lighter.signer_client', 'lighter.api_client'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='coin3.2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['coin.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='coin3.2',
)
app = BUNDLE(
    coll,
    name='coin3.2.app',
    icon='coin.ico',
    bundle_identifier=None,
)
