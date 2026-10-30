"""Windows 启动守护：父进程消失或守护器退出时，由系统终止整组后代。

不监听端口、不读取业务配置；仅使用 Python 标准库及 Windows Job Object。
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""

import ctypes
import os
import signal
import subprocess
import sys
import threading
from ctypes import wintypes


class BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimit),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def launcher_handles(kernel, parent_pid):
    """同时监测 npm/cmd 等启动链，防止只结束 npm 后 dev 本身仍然存活。"""
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    processes = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            processes[entry.th32ProcessID] = (
                entry.th32ParentProcessID,
                entry.szExeFile.lower(),
            )
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(ctypes.get_last_error())
                break
    finally:
        kernel.CloseHandle(snapshot)
    handles, seen = [], set()
    launchers = {"node.exe", "cmd.exe", "python.exe", "pwsh.exe", "powershell.exe"}
    while parent_pid and parent_pid not in seen:
        seen.add(parent_pid)
        ancestor, name = processes.get(parent_pid, (0, ""))
        if handles and name not in launchers:
            break
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)
        parent_pid = ancestor
    return handles


def attach_job(parent_pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": (
            [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
            wintypes.HANDLE,
        ),
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": (
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "GetCurrentProcess": ([], wintypes.HANDLE),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        "Process32FirstW": (
            [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)],
            wintypes.BOOL,
        ),
        "Process32NextW": (
            [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)],
            wintypes.BOOL,
        ),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    # 持有真实父进程句柄，不按 PID 轮询，避免 PID 重用后误认进程。
    parents = launcher_handles(kernel, parent_pid)
    job = kernel.CreateJobObjectW(None, None)  # 默认句柄不继承给后代
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(
        job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(job)
        raise error
    # 守护器先加入 Job，再创建业务进程，避免启动与归组之间留下逃逸窗口。
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(job)
        raise error

    def watch_parent(parent):
        kernel.WaitForSingleObject(parent, 0xFFFFFFFF)
        os._exit(1)  # 系统关闭唯一 Job 句柄，连同本守护器终止全部后代

    for parent in parents:
        threading.Thread(target=watch_parent, args=(parent,), daemon=True).start()
    return job


def main():
    if sys.platform != "win32" or len(sys.argv) < 3:
        raise RuntimeError("此守护器仅供 Windows 启动脚本调用")
    job = attach_job(int(sys.argv[1]))
    for event in (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK):
        signal.signal(event, lambda *_: os._exit(130))
    child = subprocess.Popen(
        sys.argv[2:], env={**os.environ, "INVOICE_MANAGED_JOB": "1"}
    )
    code = child.wait()
    # Job 包含守护器自身，退出由系统关闭句柄；即使主子进程先退，也会清理孙进程。
    assert job
    os._exit(code if code < 0x80000000 else code - 0x100000000)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(
            f"Windows 子进程管理失败，未继续运行：{error}", file=sys.stderr, flush=True
        )
        os._exit(1)
