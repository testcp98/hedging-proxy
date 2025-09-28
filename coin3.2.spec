# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 获取虚拟环境路径
venv_path = os.path.join(os.getcwd(), '.venv')
site_packages = os.path.join(venv_path, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
lighter_path = os.path.join(site_packages, 'lighter')

# 手动指定 lighter 的动态库文件
lighter_binaries = []
if os.path.exists(lighter_path):
    signers_path = os.path.join(lighter_path, 'signers')
    if os.path.exists(signers_path):
        for file in os.listdir(signers_path):
            if file.endswith(('.dylib', '.so')):
                src = os.path.join(signers_path, file)
                dst = os.path.join('lighter', 'signers', file)
                lighter_binaries.append((src, dst))

# 收集 lighter 库的数据文件
lighter_data = collect_data_files('lighter')

a = Analysis(
    ['coin.py'],
    pathex=[venv_path],
    binaries=lighter_binaries,
    datas=lighter_data,
    hiddenimports=[
        'lighter', 
        'lighter.signers', 
        'lighter.api', 
        'lighter.models',
        'lighter.signer_client',
        'lighter.ws_client',
        'lighter.rest',
        'lighter.configuration',
        'lighter.nonce_manager',
        'lighter.errors',
        'lighter.exceptions',
        'lighter.api_response',
        'lighter.transactions'
    ],
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
