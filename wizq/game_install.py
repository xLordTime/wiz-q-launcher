"""Locate Wizard101 installations without choosing a different copy at launch."""

import ctypes
import os
import sys
from itertools import chain
from pathlib import Path

CLIENT = Path("Bin", "WizardGraphicalClient.exe")
PATCHER = "Wizard101.exe"
UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


def install_folder(value):
    path = Path(os.path.expandvars(str(value).strip().strip('"')))
    if not path.is_absolute():
        raise ValueError("Wähle einen vollständigen Spielpfad, zum Beispiel A:\\Spiele\\Wizard101(DE).")
    name = path.name.casefold()
    if name == CLIENT.name.casefold():
        if path.parent.name.casefold() != "bin":
            raise ValueError("Wähle die Clientdatei im Bin-Ordner der Wizard101-Installation.")
        return path.parent.parent
    if name in ("bin", PATCHER.casefold()):
        return path.parent
    return path


def is_steam_install(folder):
    names = [part.casefold() for part in folder.parts]
    return ("steamapps", "common") in zip(names, names[1:])


def local_drives():
    if sys.platform != "win32":
        return []
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    try:
        drives = os.listdrives()
    except OSError:
        return []
    # Include fixed disks and removable storage. Windows can assign any drive letter.
    return [Path(drive) for drive in drives if get_drive_type(drive) in (2, 3)]


def registered_folders():
    if sys.platform != "win32":
        return
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            access = winreg.KEY_READ | view
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, access) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            name = winreg.EnumKey(key, index)
                            with winreg.OpenKey(key, name, 0, access) as entry:
                                title, _ = winreg.QueryValueEx(entry, "DisplayName")
                                if isinstance(title, str) and "wizard101" in title.lower().replace(" ", ""):
                                    folder, _ = winreg.QueryValueEx(entry, "InstallLocation")
                                    if isinstance(folder, str) and folder.strip():
                                        yield folder
                        except OSError:
                            continue
            except OSError:
                continue


def common_folders():
    parents = [
        Path(value)
        for name in ("ProgramData", "ProgramFiles", "ProgramFiles(x86)")
        if (value := os.environ.get(name))
    ]
    parents.extend(
        drive / folder
        for drive in local_drives()
        for folder in ("", "Games", "Spiele", "ProgramData", "Program Files", "Program Files (x86)")
    )
    roots = dict.fromkeys(
        folder for parent in parents for folder in (parent, parent / "KingsIsle Entertainment")
    )
    for root in roots:
        yield root
        try:
            yield from root.glob("Wizard101*")
        except OSError:
            continue


def detect_installs():
    checked, found = set(), []
    for value in chain(registered_folders(), common_folders()):
        try:
            folder = install_folder(value)
            if folder in checked:
                continue
            checked.add(folder)
            if not is_steam_install(folder) and ((folder / CLIENT).is_file() or (folder / PATCHER).is_file()):
                found.append(folder)
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda folder: str(folder).casefold())
