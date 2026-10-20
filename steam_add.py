#!/usr/bin/env python3
"""Add or update a non-Steam shortcut on SteamOS, with its library art.

    steam_add.py NAME EXE [ART_DIR]

Standard library only, so SteamOS updates can't break it.
"""
import copy
import os
import shutil
import struct
import time
import zlib

# Binary VDF: each value is <type byte> key\0 <payload>; a map ends with END.
MAP, STRING, INT32, FLOAT32, UINT64, END = 0x00, 0x01, 0x02, 0x03, 0x07, 0x08


class Float32(float):
    pass


class UInt64(int):
    pass


def loads(data):
    doc, pos = _read_map(data, 0)
    if pos != len(data):
        raise ValueError("trailing bytes after the top-level map")
    return doc


def _read_cstr(data, pos):
    end = data.find(b"\x00", pos)
    if end < 0:
        raise ValueError("unterminated string at byte %d" % pos)
    return data[pos:end].decode("utf-8"), end + 1


def _read_map(data, pos):
    out = {}
    while True:
        if pos >= len(data):
            raise ValueError("file ends inside a map")
        kind = data[pos]
        pos += 1
        if kind == END:
            return out, pos
        key, pos = _read_cstr(data, pos)
        if kind == MAP:
            out[key], pos = _read_map(data, pos)
        elif kind == STRING:
            out[key], pos = _read_cstr(data, pos)
        elif kind == INT32:
            out[key] = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        elif kind == FLOAT32:
            out[key] = Float32(struct.unpack_from("<f", data, pos)[0])
            pos += 4
        elif kind == UINT64:
            out[key] = UInt64(struct.unpack_from("<Q", data, pos)[0])
            pos += 8
        else:
            raise ValueError("unknown type 0x%02x at byte %d" % (kind, pos - 1))
        if pos > len(data):
            raise ValueError("file ends inside %r" % key)


def dumps(doc):
    return _write_map(doc)


def _write_map(doc):
    out = bytearray()
    for key, value in doc.items():
        k = key.encode("utf-8") + b"\x00"
        if isinstance(value, dict):
            out += bytes([MAP]) + k + _write_map(value)
        elif isinstance(value, str):
            out += bytes([STRING]) + k + value.encode("utf-8") + b"\x00"
        elif isinstance(value, Float32):
            out += bytes([FLOAT32]) + k + struct.pack("<f", value)
        elif isinstance(value, UInt64):
            out += bytes([UINT64]) + k + struct.pack("<Q", value)
        elif isinstance(value, int):
            out += bytes([INT32]) + k + struct.pack("<I", value & 0xFFFFFFFF)
        else:
            raise TypeError("can't write %r = %r" % (key, value))
    return bytes(out + bytes([END]))


def _get(entry, key):
    """Steam isn't consistent about key case (appid, AppName, Exe, exe)."""
    for k, v in entry.items():
        if k.lower() == key.lower():
            return k, v
    return key, None


def _quote(path):
    return '"%s"' % path


def upsert(doc, name, exe, icon=None):
    """Add the shortcut for exe, or bring the existing one up to date. Returns (appid, changed).
    icon=None leaves the current icon alone."""
    shortcuts = doc.setdefault("shortcuts", {})
    wanted = {"AppName": name, "Exe": _quote(exe), "StartDir": _quote(os.path.dirname(exe))}
    if icon is not None:
        wanted["icon"] = icon
    for entry in shortcuts.values():
        if (_get(entry, "Exe")[1] or "").strip('"') != exe:
            continue
        changed = False
        for key, value in wanted.items():
            real_key, current = _get(entry, key)
            if current != value:
                entry[real_key] = value
                changed = True
        return _get(entry, "appid")[1], changed
    appid = zlib.crc32((wanted["Exe"] + name).encode("utf-8")) | 0x80000000
    shortcuts[str(len(shortcuts))] = {
        "appid": appid, "icon": "", **wanted,
        "ShortcutPath": "", "LaunchOptions": "", "IsHidden": 0, "AllowDesktopConfig": 1,
        "AllowOverlay": 1, "OpenVR": 0, "Devkit": 0, "DevkitGameID": "", "DevkitOverrideAppID": 0,
        "LastPlayTime": 0, "FlatpakAppID": "", "tags": {},
    }
    return appid, True


ART = {"cover": "%dp.png", "capsule": "%d.png", "hero": "%d_hero.png", "logo": "%d_logo.png", "icon": "%d_icon.png"}


def install_art(art_dir, grid_dir, appid):
    """Copy cover/capsule/hero/logo/icon.png into grid/ under Steam's names. Returns what changed."""
    changed = []
    for role, pattern in ART.items():
        src = os.path.join(art_dir or "", role + ".png")
        if not art_dir or not os.path.exists(src):
            continue
        dst = os.path.join(grid_dir, pattern % appid)
        data = open(src, "rb").read()
        if os.path.exists(dst) and open(dst, "rb").read() == data:
            continue
        os.makedirs(grid_dir, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        changed.append(dst)
    return changed


def _write_vdf(path, doc):
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S")))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dumps(doc))
    if loads(open(tmp, "rb").read()) != doc:
        raise SystemExit("refusing to write %s: it didn't read back the same" % path)
    os.replace(tmp, path)


def _read_vdf(path):
    if not os.path.exists(path):
        return {"shortcuts": {}}
    return loads(open(path, "rb").read())


def run(name, exe, art_dir, userdata, steam):
    for user in sorted(os.listdir(userdata)):
        config = os.path.join(userdata, user, "config")
        if not os.path.isdir(config):
            continue
        vdf = os.path.join(config, "shortcuts.vdf")
        grid = os.path.join(config, "grid")
        doc = _read_vdf(vdf)
        appid, _ = upsert(copy.deepcopy(doc), name, exe)
        icon = os.path.join(grid, ART["icon"] % appid)
        has_icon = art_dir and os.path.exists(os.path.join(art_dir, "icon.png"))
        icon = icon if has_icon else None
        _, shortcut_changed = upsert(doc, name, exe, icon)
        art_changed = install_art(art_dir, grid, appid)
        if not shortcut_changed and not art_changed:
            print("%s (user %s): up to date" % (name, user))
            continue
        if steam.game_running():
            raise SystemExit("a game is running; quit it and run this again so Steam can restart")
        steam.shutdown()
        if shortcut_changed:
            # Steam rewrote the file as it exited, so start again from what it left.
            doc = _read_vdf(vdf)
            upsert(doc, name, exe, icon)
            _write_vdf(vdf, doc)
        steam.wait_until_back()
        print("%s (user %s): appid %d, updated" % (name, user, appid))
