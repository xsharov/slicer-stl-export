import ctypes
import json
import sys
import time
from ctypes import wintypes

WM_TIMER = 0x0113
WM_COPYDATA = 0x004A
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
CLASS_NAME = "SlicerFakeWindow"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = wintypes.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = (
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    )


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = (("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p))


user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
)
user32.CreateWindowExW.restype = wintypes.HWND
user32.SetPropW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE)
user32.SetPropW.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p)
user32.SetTimer.restype = ctypes.c_size_t
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = (ctypes.c_int,)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def main(output, delay, hang):
    time.sleep(delay)

    def procedure(hwnd, message, wparam, lparam):
        if message == WM_COPYDATA:
            time.sleep(hang)
            data = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
            payload = ctypes.string_at(data.lpData, data.cbData)
            with open(output, "w", encoding="utf-8") as stream:
                json.dump({"id": data.dwData, "text": payload.decode("utf-16-le")}, stream)
            user32.PostQuitMessage(0)
            return 1
        if message == WM_TIMER:
            user32.PostQuitMessage(1)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    callback = WNDPROC(procedure)
    instance = kernel32.GetModuleHandleW(None)
    window_class = WNDCLASSW(lpfnWndProc=callback, hInstance=instance, lpszClassName=CLASS_NAME)
    user32.RegisterClassW(ctypes.byref(window_class))
    hwnd = user32.CreateWindowExW(
        WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        CLASS_NAME,
        "Untitled - Slicer",
        WS_POPUP,
        -32000,
        -32000,
        16,
        16,
        None,
        None,
        instance,
        None,
    )
    user32.SetPropW(hwnd, "Instance_Hash_Minor", 1)
    user32.SetPropW(hwnd, "Instance_Hash_Major", 1)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetTimer(hwnd, 1, 30000, None)
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    user32.DestroyWindow(hwnd)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 0.0)
