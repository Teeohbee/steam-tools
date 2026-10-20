import unittest

import steam_add as sa


def entry_bytes(appid, name, exe):
    """One shortcut entry, laid out by hand as Steam writes it."""
    return (b"\x00" + b"0\x00"
            + b"\x02appid\x00" + appid.to_bytes(4, "little")
            + b"\x01AppName\x00" + name.encode() + b"\x00"
            + b"\x01Exe\x00" + exe.encode() + b"\x00"
            + b"\x02IsHidden\x00" + (0).to_bytes(4, "little")
            + b"\x00tags\x00" + b"\x08"
            + b"\x08")


def file_bytes(*entries):
    return b"\x00shortcuts\x00" + b"".join(entries) + b"\x08\x08"


SCUTTLE = file_bytes(entry_bytes(2537009592, "Scuttle", '"/home/deck/Games/Scuttle/launch.sh"'))


class ReadTest(unittest.TestCase):
    def test_reads_an_entry_as_steam_writes_it(self):
        doc = sa.loads(SCUTTLE)
        entry = doc["shortcuts"]["0"]
        self.assertEqual(entry["appid"], 2537009592)
        self.assertEqual(entry["AppName"], "Scuttle")
        self.assertEqual(entry["Exe"], '"/home/deck/Games/Scuttle/launch.sh"')
        self.assertEqual(entry["tags"], {})

    def test_an_empty_file_has_no_shortcuts(self):
        self.assertEqual(sa.loads(file_bytes())["shortcuts"], {})

    def test_rejects_a_truncated_file(self):
        with self.assertRaises(ValueError):
            sa.loads(SCUTTLE[:-3])


class RoundTripTest(unittest.TestCase):
    def test_writes_back_the_exact_bytes_it_read(self):
        self.assertEqual(sa.dumps(sa.loads(SCUTTLE)), SCUTTLE)

    def test_keeps_types_it_does_not_otherwise_use(self):
        raw = (b"\x00shortcuts\x00\x000\x00"
               + b"\x07LastPlayTime64\x00" + (2 ** 40).to_bytes(8, "little")
               + b"\x03Volume\x00" + bytes([0, 0, 0x80, 0x3F])
               + b"\x08\x08\x08")
        self.assertEqual(sa.dumps(sa.loads(raw)), raw)


if __name__ == "__main__":
    unittest.main()
