import unittest

import steam_add


def shortcut_bytes(appid, name, exe):
    """One shortcut, laid out byte by byte the way Steam writes it."""
    return (b"\x00" + b"0\x00"
            + b"\x02appid\x00" + appid.to_bytes(4, "little")
            + b"\x01AppName\x00" + name.encode() + b"\x00"
            + b"\x01Exe\x00" + exe.encode() + b"\x00"
            + b"\x02IsHidden\x00" + (0).to_bytes(4, "little")
            + b"\x00tags\x00" + b"\x08"
            + b"\x08")


def shortcuts_file_bytes(*shortcuts):
    return b"\x00shortcuts\x00" + b"".join(shortcuts) + b"\x08\x08"


SCUTTLE_FILE = shortcuts_file_bytes(shortcut_bytes(2537009592, "Scuttle", '"/home/deck/Games/Scuttle/launch.sh"'))


class ReadingTest(unittest.TestCase):
    def test_reads_a_shortcut_as_steam_writes_it(self):
        document = steam_add.parse_vdf(SCUTTLE_FILE)
        shortcut = document["shortcuts"]["0"]
        self.assertEqual(shortcut["appid"], 2537009592)
        self.assertEqual(shortcut["AppName"], "Scuttle")
        self.assertEqual(shortcut["Exe"], '"/home/deck/Games/Scuttle/launch.sh"')
        self.assertEqual(shortcut["tags"], {})

    def test_an_empty_file_has_no_shortcuts(self):
        document = steam_add.parse_vdf(shortcuts_file_bytes())
        self.assertEqual(document["shortcuts"], {})

    def test_rejects_a_file_that_is_cut_short(self):
        with self.assertRaises(ValueError):
            steam_add.parse_vdf(SCUTTLE_FILE[:-3])


class RoundTripTest(unittest.TestCase):
    def test_writes_back_exactly_the_bytes_it_read(self):
        document = steam_add.parse_vdf(SCUTTLE_FILE)
        self.assertEqual(steam_add.serialise_vdf(document), SCUTTLE_FILE)

    def test_keeps_number_types_it_does_not_otherwise_use(self):
        file_bytes = (b"\x00shortcuts\x00\x000\x00"
                      + b"\x07LastPlayTime64\x00" + (2 ** 40).to_bytes(8, "little")
                      + b"\x03Volume\x00" + bytes([0, 0, 0x80, 0x3F])
                      + b"\x08\x08\x08")
        document = steam_add.parse_vdf(file_bytes)
        self.assertEqual(steam_add.serialise_vdf(document), file_bytes)


if __name__ == "__main__":
    unittest.main()
