"""
PyInstaller hook for passlib
"""

from PyInstaller.utils.hooks import collect_submodules

# Включаем все подмодули passlib
hiddenimports = collect_submodules('passlib')
