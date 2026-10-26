#!/usr/bin/env python3
"""Add or update a non-Steam shortcut on SteamOS, with its library art.

    python3 steam_add.py NAME EXE_PATH [ART_FOLDER]

Standard library only, so SteamOS updates can't break it.
"""
import argparse
import os
import shutil
import struct
import subprocess
import time
import zlib

# Steam's shortcuts.vdf is "binary VDF". Every value is written as:
#   <one type byte> <key> 0x00 <the value>
# A map is a list of values that ends with the END_OF_MAP byte.
TYPE_MAP = 0x00
TYPE_STRING = 0x01
TYPE_INT32 = 0x02
TYPE_FLOAT32 = 0x03
TYPE_UINT64 = 0x07
END_OF_MAP = 0x08

STEAM_USERDATA_FOLDER = os.path.expanduser("~/.local/share/Steam/userdata")

# Steam's file name for each piece of art, given the shortcut's appid.
ART_FILE_NAMES = {
    "cover": "{appid}p.png",
    "capsule": "{appid}.png",
    "hero": "{appid}_hero.png",
    "logo": "{appid}_logo.png",
    "icon": "{appid}_icon.png",
}


# Python has one int and one float type, but the file has several. These two
# wrappers remember which type a number was read as, so it's written back the same way.
class Float32(float):
    pass


class UInt64(int):
    pass


# --- Reading and writing binary VDF -------------------------------------------------

def parse_vdf(file_bytes):
    document, position = read_map(file_bytes, 0)
    if position != len(file_bytes):
        raise ValueError("unexpected bytes after the end of the file's top-level map")
    return document


def read_null_terminated_string(file_bytes, position):
    end = file_bytes.find(b"\x00", position)
    if end == -1:
        raise ValueError("a string starting at byte %d never ends" % position)
    text = file_bytes[position:end].decode("utf-8")
    position_after_string = end + 1
    return text, position_after_string


def read_map(file_bytes, position):
    """Read values until END_OF_MAP. Returns the map and the position just after it."""
    result = {}
    while True:
        if position >= len(file_bytes):
            raise ValueError("the file ends in the middle of a map")
        value_type = file_bytes[position]
        position += 1
        if value_type == END_OF_MAP:
            return result, position

        key, position = read_null_terminated_string(file_bytes, position)

        if value_type == TYPE_MAP:
            result[key], position = read_map(file_bytes, position)
        elif value_type == TYPE_STRING:
            result[key], position = read_null_terminated_string(file_bytes, position)
        elif value_type == TYPE_INT32:
            # "<I" means a little-endian unsigned 32-bit integer
            result[key] = struct.unpack_from("<I", file_bytes, position)[0]
            position += 4
        elif value_type == TYPE_FLOAT32:
            result[key] = Float32(struct.unpack_from("<f", file_bytes, position)[0])
            position += 4
        elif value_type == TYPE_UINT64:
            result[key] = UInt64(struct.unpack_from("<Q", file_bytes, position)[0])
            position += 8
        else:
            raise ValueError("unknown value type 0x%02x at byte %d" % (value_type, position - 1))

        if position > len(file_bytes):
            raise ValueError("the file ends in the middle of %r" % key)


def serialise_vdf(document):
    return write_map(document)


def write_map(document):
    output = bytearray()
    for key, value in document.items():
        key_bytes = key.encode("utf-8") + b"\x00"
        # Check Float32 and UInt64 before plain int, because they are also ints/floats.
        if isinstance(value, dict):
            output += bytes([TYPE_MAP]) + key_bytes + write_map(value)
        elif isinstance(value, str):
            output += bytes([TYPE_STRING]) + key_bytes + value.encode("utf-8") + b"\x00"
        elif isinstance(value, Float32):
            output += bytes([TYPE_FLOAT32]) + key_bytes + struct.pack("<f", value)
        elif isinstance(value, UInt64):
            output += bytes([TYPE_UINT64]) + key_bytes + struct.pack("<Q", value)
        elif isinstance(value, int):
            output += bytes([TYPE_INT32]) + key_bytes + struct.pack("<I", value)
        else:
            raise TypeError("don't know how to write %r = %r" % (key, value))
    output += bytes([END_OF_MAP])
    return bytes(output)


# --- Shortcuts ----------------------------------------------------------------------

def find_key_ignoring_case(shortcut, wanted_key):
    """Steam isn't consistent about key case (appid, AppName, Exe or exe), so match any."""
    for key in shortcut.keys():
        if key.lower() == wanted_key.lower():
            return key
    return None


def value_ignoring_case(shortcut, wanted_key):
    key = find_key_ignoring_case(shortcut, wanted_key)
    if key is None:
        return None
    return shortcut[key]


def in_quotes(path):
    # Steam stores Exe and StartDir with quotes round them
    return '"' + path + '"'


def find_shortcut_by_exe(document, exe_path):
    shortcuts = document.get("shortcuts", {})
    for shortcut in shortcuts.values():
        stored_exe = value_ignoring_case(shortcut, "Exe")
        if stored_exe is not None and stored_exe.strip('"') == exe_path:
            return shortcut
    return None


def appid_for(document, name, exe_path):
    """An existing shortcut keeps its appid. A new one gets the usual crc32-based id."""
    existing_shortcut = find_shortcut_by_exe(document, exe_path)
    if existing_shortcut is not None:
        return value_ignoring_case(existing_shortcut, "appid")
    checksum = zlib.crc32((in_quotes(exe_path) + name).encode("utf-8"))
    return checksum | 0x80000000


def means_the_same(setting, stored_value, wanted_value):
    """Paths count as the same with or without quotes or a trailing slash, so a shortcut
    written by Steam (or by hand) isn't rewritten, and Steam restarted, just to reformat it."""
    if setting in ("Exe", "StartDir") and stored_value is not None:
        stored_path = stored_value.strip('"').rstrip("/")
        wanted_path = wanted_value.strip('"').rstrip("/")
        return stored_path == wanted_path
    return stored_value == wanted_value


def add_or_update_shortcut(document, name, exe_path, icon_path=None):
    """Make the shortcut for exe_path match these settings. Returns True if anything changed.
    icon_path=None leaves the shortcut's current icon alone."""
    wanted_settings = {
        "AppName": name,
        "Exe": in_quotes(exe_path),
        "StartDir": in_quotes(os.path.dirname(exe_path)),
    }
    if icon_path is not None:
        wanted_settings["icon"] = icon_path

    existing_shortcut = find_shortcut_by_exe(document, exe_path)

    if existing_shortcut is None:
        new_shortcut = {
            "appid": appid_for(document, name, exe_path),
            "AppName": name,
            "Exe": in_quotes(exe_path),
            "StartDir": in_quotes(os.path.dirname(exe_path)),
            "icon": icon_path if icon_path is not None else "",
            "ShortcutPath": "",
            "LaunchOptions": "",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "FlatpakAppID": "",
            "tags": {},
        }
        shortcuts = document.setdefault("shortcuts", {})
        next_index = str(len(shortcuts))   # Steam keys its shortcuts "0", "1", "2", ...
        shortcuts[next_index] = new_shortcut
        return True

    anything_changed = False
    for setting, wanted_value in wanted_settings.items():
        key_as_stored = find_key_ignoring_case(existing_shortcut, setting) or setting
        if not means_the_same(setting, existing_shortcut.get(key_as_stored), wanted_value):
            existing_shortcut[key_as_stored] = wanted_value
            anything_changed = True
    return anything_changed


# --- Files --------------------------------------------------------------------------

def read_shortcuts_file(shortcuts_file):
    if not os.path.exists(shortcuts_file):
        return {"shortcuts": {}}
    with open(shortcuts_file, "rb") as file:
        return parse_vdf(file.read())


def back_up_and_write_shortcuts_file(shortcuts_file, document):
    if os.path.exists(shortcuts_file):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(shortcuts_file, shortcuts_file + ".bak-" + timestamp)

    # Write to a temporary file, check it reads back the same, then swap it in.
    temporary_file = shortcuts_file + ".tmp"
    with open(temporary_file, "wb") as file:
        file.write(serialise_vdf(document))
    with open(temporary_file, "rb") as file:
        reads_back_the_same = parse_vdf(file.read()) == document
    if not reads_back_the_same:
        raise SystemExit("refusing to write %s: it didn't read back the same" % shortcuts_file)
    os.replace(temporary_file, shortcuts_file)


def art_needing_copying(art_folder, grid_folder, appid):
    """Which of cover/capsule/hero/logo/icon.png differ from what's in Steam's grid folder.
    Skips missing and unchanged files. Returns (source, destination) pairs; copies nothing."""
    files_to_copy = []
    if art_folder is None:
        return files_to_copy
    for role, steam_file_name in ART_FILE_NAMES.items():
        source = os.path.join(art_folder, role + ".png")
        if not os.path.exists(source):
            continue
        destination = os.path.join(grid_folder, steam_file_name.format(appid=appid))
        if os.path.exists(destination):
            with open(source, "rb") as source_file, open(destination, "rb") as destination_file:
                if source_file.read() == destination_file.read():
                    continue
        files_to_copy.append((source, destination))
    return files_to_copy


def copy_art_into_grid(files_to_copy, grid_folder):
    os.makedirs(grid_folder, exist_ok=True)
    for source, destination in files_to_copy:
        shutil.copyfile(source, destination)


# --- The whole job ------------------------------------------------------------------

def add_to_steam(name, exe_path, art_folder, userdata_folder, steam):
    """Add or update the shortcut and its art for every Steam user on this device."""
    for steam_user_id in sorted(os.listdir(userdata_folder)):
        config_folder = os.path.join(userdata_folder, steam_user_id, "config")
        if not os.path.isdir(config_folder):
            continue
        shortcuts_file = os.path.join(config_folder, "shortcuts.vdf")
        grid_folder = os.path.join(config_folder, "grid")

        document = read_shortcuts_file(shortcuts_file)
        appid = appid_for(document, name, exe_path)

        icon_path = None   # None means: leave the shortcut's icon as it is
        if art_folder is not None and os.path.exists(os.path.join(art_folder, "icon.png")):
            icon_path = os.path.join(grid_folder, ART_FILE_NAMES["icon"].format(appid=appid))

        shortcut_changed = add_or_update_shortcut(document, name, exe_path, icon_path)
        art_to_copy = art_needing_copying(art_folder, grid_folder, appid)

        if not shortcut_changed and len(art_to_copy) == 0:
            print("%s (Steam user %s): already up to date" % (name, steam_user_id))
            continue

        # Steam only notices changes when it starts, so it has to restart. Nothing is
        # written before this check, so a refused run leaves the change for the next one.
        if steam.is_game_running():
            raise SystemExit("a game is running; quit it and run this again so Steam can restart")

        # Write everything before restarting: Game Mode relaunches Steam within seconds,
        # leaving no gap to write in. Steam writes shortcuts.vdf when its own shortcuts
        # change (a launch updates LastPlayTime), not when it exits, so the edit survives.
        copy_art_into_grid(art_to_copy, grid_folder)
        if shortcut_changed:
            back_up_and_write_shortcuts_file(shortcuts_file, document)
        steam.restart()
        print("%s (Steam user %s): updated, appid %d" % (name, steam_user_id, appid))


class Steam:
    """The real Steam client, driven from an SSH session."""
    RUNNING_GAME_PROCESS = "SteamLaunch AppId="

    def is_game_running(self):
        result = subprocess.run(["pgrep", "-f", self.RUNNING_GAME_PROCESS], stdout=subprocess.DEVNULL)
        return result.returncode == 0

    def restart(self):
        old_client = self.client_process_id()
        if old_client is None:
            print("Steam isn't running; the changes will show when it starts")
            return
        subprocess.run(["steam", "-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Game Mode relaunches Steam by itself, so it's back when there's a new client process.
        # Desktop Mode doesn't relaunch it.
        came_back = self.wait_for(lambda: self.client_process_id() not in (None, old_client), seconds=90)
        if not came_back:
            print("Steam hasn't come back; start it yourself to see the changes")

    def client_process_id(self):
        # Matched by exact process name: Steam's helpers also live under ubuntu12_32/steam*
        # and outlive the client, so matching the path never sees Steam stop.
        result = subprocess.run(["pgrep", "-x", "steam"], stdout=subprocess.PIPE, text=True)
        process_ids = result.stdout.split()
        return process_ids[0] if process_ids else None

    def wait_for(self, condition, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(1)
        return False


def main():
    parser = argparse.ArgumentParser(description="Add or update a non-Steam shortcut and its library art.")
    parser.add_argument("name", help="the name shown in the Steam library")
    parser.add_argument("exe_path", help="path to the game's launcher")
    parser.add_argument("art_folder", nargs="?", help="folder holding cover/capsule/hero/logo/icon.png")
    parser.add_argument("--userdata", default=STEAM_USERDATA_FOLDER, help="Steam's userdata folder")
    arguments = parser.parse_args()
    add_to_steam(arguments.name, os.path.abspath(arguments.exe_path), arguments.art_folder,
                 arguments.userdata, Steam())


if __name__ == "__main__":
    main()
