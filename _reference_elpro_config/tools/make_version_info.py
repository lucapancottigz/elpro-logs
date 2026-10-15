# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Génère build/version_info.txt (ressource de version Windows pour PyInstaller) à partir de version.py."""
import os, sys
ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, '..'))
from version import APP_VERSION, APP_COMPANY, APP_COPYRIGHT

n = [int(x) for x in APP_VERSION.split('.')] + [0]
modele = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers=({n[0]}, {n[1]}, {n[2]}, 0), prodvers=({n[0]}, {n[1]}, {n[2]}, 0),
                    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', {APP_COMPANY!r}),
      StringStruct('FileDescription', 'ELPRO Config'),
      StringStruct('FileVersion', {APP_VERSION!r}),
      StringStruct('InternalName', 'ELPRO Config'),
      StringStruct('LegalCopyright', {APP_COPYRIGHT!r}),
      StringStruct('OriginalFilename', 'ELPRO Config.exe'),
      StringStruct('ProductName', 'ELPRO Config'),
      StringStruct('ProductVersion', {APP_VERSION!r})])]),
        VarFileInfo([VarStruct('Translation', [0x040C, 1200])])]
)
'''
os.makedirs(os.path.join(ICI, '..', 'build'), exist_ok=True)
with open(os.path.join(ICI, '..', 'build', 'version_info.txt'), 'w', encoding='utf-8') as f:
    f.write(modele)
print('build/version_info.txt créé')
