#!/usr/bin/env python3
"""Add or update a non-Steam shortcut on SteamOS, with its library art.

    steam_add.py NAME EXE [ART_DIR]

Standard library only, so SteamOS updates can't break it.
"""
import struct

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
