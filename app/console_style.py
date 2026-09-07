"""Restrained terminal accents; plain text when redirected or unsupported."""
import os
import sys


def enable_colors():
    if not sys.stdout.isatty() or 'NO_COLOR' in os.environ:
        return False
    if os.name != 'nt':
        return os.environ.get('TERM') != 'dumb'
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.GetStdHandle(wintypes.DWORD(-11))
        mode = wintypes.DWORD()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and
                    kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, AttributeError):
        return False


ENABLED = enable_colors()
COLORS = {'heading': '36', 'success': '32', 'warning': '33', 'error': '31'}


def accent(text, kind='heading'):
    text = str(text)
    return f'\033[{COLORS[kind]}m{text}\033[0m' if ENABLED else text


def notice(text, kind='heading'):
    print(accent(text, kind))
