"""
PyInstaller hook for passlib
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('passlib')
