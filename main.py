"""Helper modes never create a GUI or open the profile."""

import sys


def restore_helper_stdio():
    # PyInstaller --windowed sets stdio to None, even when the parent supplied
    # pipes. Reopen only inherited handles in helper mode; never create a console.
    if sys.platform != "win32":
        return
    import ctypes
    import msvcrt
    import os

    get_handle = ctypes.windll.kernel32.GetStdHandle
    get_handle.argtypes = [ctypes.c_ulong]
    get_handle.restype = ctypes.c_void_p
    for name, number, flags, mode in (
        ("stdin", -10, os.O_RDONLY, "r"),
        ("stdout", -11, os.O_WRONLY, "w"),
        ("stderr", -12, os.O_WRONLY, "w"),
    ):
        if getattr(sys, name) is None:
            handle = get_handle(number & 0xFFFFFFFF)
            if handle and handle != ctypes.c_void_p(-1).value:
                fd = msvcrt.open_osfhandle(handle, flags)
                setattr(sys, name, os.fdopen(fd, mode, encoding="utf-8", closefd=False))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--login-worker", "--addon-worker"):
        restore_helper_stdio()
    if len(sys.argv) > 1 and sys.argv[1] == "--login-worker":
        from wizq.backend import login_worker

        return login_worker()
    if len(sys.argv) == 3 and sys.argv[1] == "--apply-update":
        from wizq.updates import apply_worker

        return apply_worker(sys.argv[2])
    if len(sys.argv) == 5 and sys.argv[1] == "--addon-worker" and sys.argv[3] == "--addon-data":
        from wizq.addons import worker_main

        return worker_main(sys.argv[2], sys.argv[4])
    from wizq.app import main as qt_main

    return qt_main()


if __name__ == "__main__":
    raise SystemExit(main())
