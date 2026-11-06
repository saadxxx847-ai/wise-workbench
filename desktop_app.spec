# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
data = [(str(root / 'templates'), 'templates'), (str(root / 'static'), 'static')]
data += collect_data_files('webview')
a = Analysis([str(root / 'desktop_app.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['webview.platforms.qt', 'webview.platforms.gtk', 'webview.platforms.cocoa',
                       'webview.platforms.cef', 'webview.platforms.android', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='哲店长工作台',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, icon=str(root / 'static' / 'app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='哲店长工作台')
