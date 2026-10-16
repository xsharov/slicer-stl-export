import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WM_COPYDATA = 0x004A
_SMTO_ABORTIFHUNG = 0x0002
_SW_RESTORE = 9
_FILETIME_TICKS_PER_SECOND = 10_000_000
_MAIN_WINDOW_PROPERTIES = ("Instance_Hash_Minor", "Instance_Hash_Major")


class _WtsProcessInfo(ctypes.Structure):
    _fields_ = (
        ("SessionId", wintypes.DWORD),
        ("ProcessId", wintypes.DWORD),
        ("pProcessName", wintypes.LPWSTR),
        ("pUserSid", ctypes.c_void_p),
    )


class _CopyData(ctypes.Structure):
    _fields_ = (
        ("dwData", ctypes.c_size_t),
        ("cbData", wintypes.DWORD),
        ("lpData", ctypes.c_void_p),
    )


_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _bind(function, argtypes, restype):
    function.argtypes = argtypes
    function.restype = restype


_bind(
    _wtsapi32.WTSEnumerateProcessesW,
    (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_WtsProcessInfo)),
        ctypes.POINTER(wintypes.DWORD),
    ),
    wintypes.BOOL,
)
_bind(_wtsapi32.WTSFreeMemory, (ctypes.c_void_p,), None)
_bind(_kernel32.OpenProcess, (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD), wintypes.HANDLE)
_bind(
    _kernel32.QueryFullProcessImageNameW,
    (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)),
    wintypes.BOOL,
)
_bind(
    _kernel32.GetProcessTimes,
    (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ),
    wintypes.BOOL,
)
_bind(_kernel32.GetSystemTimeAsFileTime, (ctypes.POINTER(wintypes.FILETIME),), None)
_bind(_kernel32.ProcessIdToSessionId, (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL)
_bind(_kernel32.GetCurrentProcessId, (), wintypes.DWORD)
_bind(_kernel32.CloseHandle, (wintypes.HANDLE,), wintypes.BOOL)
_bind(_user32.EnumWindows, (_EnumWindowsProc, wintypes.LPARAM), wintypes.BOOL)
_bind(_user32.GetWindowThreadProcessId, (wintypes.HWND, ctypes.POINTER(wintypes.DWORD)), wintypes.DWORD)
_bind(_user32.IsWindowVisible, (wintypes.HWND,), wintypes.BOOL)
_bind(_user32.GetPropW, (wintypes.HWND, wintypes.LPCWSTR), wintypes.HANDLE)
_bind(_user32.IsIconic, (wintypes.HWND,), wintypes.BOOL)
_bind(_user32.ShowWindow, (wintypes.HWND, ctypes.c_int), wintypes.BOOL)
_bind(_user32.SetForegroundWindow, (wintypes.HWND,), wintypes.BOOL)
_bind(_user32.AllowSetForegroundWindow, (wintypes.DWORD,), wintypes.BOOL)
_bind(
    _user32.SendMessageTimeoutW,
    (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ),
    wintypes.LPARAM,
)


def current_session():
    session = wintypes.DWORD()
    if _kernel32.ProcessIdToSessionId(_kernel32.GetCurrentProcessId(), ctypes.byref(session)):
        return session.value
    return None


def processes():
    info = ctypes.POINTER(_WtsProcessInfo)()
    count = wintypes.DWORD()
    if not _wtsapi32.WTSEnumerateProcessesW(None, 0, 1, ctypes.byref(info), ctypes.byref(count)):
        return []
    try:
        return [(info[i].ProcessId, info[i].SessionId, info[i].pProcessName or "") for i in range(count.value)]
    finally:
        _wtsapi32.WTSFreeMemory(info)


def process_ids(executable_name):
    name = executable_name.lower()
    session = current_session()
    return {pid for pid, owner, image in processes() if owner == session and image.lower() == name}


def process_path(pid):
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        _kernel32.CloseHandle(handle)


def process_age(pid):
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not _kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
    finally:
        _kernel32.CloseHandle(handle)
    now = wintypes.FILETIME()
    _kernel32.GetSystemTimeAsFileTime(ctypes.byref(now))
    return (_ticks(now) - _ticks(created)) / _FILETIME_TICKS_PER_SECOND


def _ticks(filetime):
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def main_windows(pids):
    found = []

    def visit(hwnd, _):
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and _user32.IsWindowVisible(hwnd):
            if any(_user32.GetPropW(hwnd, name) for name in _MAIN_WINDOW_PROPERTIES):
                found.append((hwnd, pid.value))
        return True

    _user32.EnumWindows(_EnumWindowsProc(visit), 0)
    return found


def allow_foreground(pid):
    _user32.AllowSetForegroundWindow(pid)


def send_copy_data(hwnd, identifier, payload, timeout_ms):
    buffer = ctypes.create_string_buffer(payload, len(payload))
    data = _CopyData(identifier, len(payload), ctypes.cast(buffer, ctypes.c_void_p))
    result = ctypes.c_size_t()
    sent = _user32.SendMessageTimeoutW(
        hwnd,
        _WM_COPYDATA,
        0,
        ctypes.addressof(data),
        _SMTO_ABORTIFHUNG,
        timeout_ms,
        ctypes.byref(result),
    )
    return bool(sent)


def activate(hwnd):
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)
