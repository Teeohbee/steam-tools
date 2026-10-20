import unittest
import zlib

import steam_add as sa
from tests.test_vdf import SCUTTLE, entry_bytes, file_bytes

EXE = "/home/deck/Games/Scuttle/launch.sh"
ICON = "/home/deck/.local/share/Steam/userdata/1/config/grid/2537009592_icon.png"


class UpsertTest(unittest.TestCase):
    def setUp(self):
        self.doc = sa.loads(SCUTTLE)

    def test_a_matching_shortcut_keeps_its_appid(self):
        appid, _ = sa.upsert(self.doc, "Scuttle", EXE)
        self.assertEqual(appid, 2537009592)
        self.assertEqual(len(self.doc["shortcuts"]), 1)

    def test_running_twice_changes_nothing_the_second_time(self):
        sa.upsert(self.doc, "Scuttle", EXE, icon=ICON)
        before = sa.dumps(self.doc)
        _, changed = sa.upsert(self.doc, "Scuttle", EXE, icon=ICON)
        self.assertFalse(changed)
        self.assertEqual(sa.dumps(self.doc), before)

    def test_renames_a_shortcut_found_by_its_exe(self):
        _, changed = sa.upsert(self.doc, "Scuttle!", EXE)
        self.assertTrue(changed)
        self.assertEqual(self.doc["shortcuts"]["0"]["AppName"], "Scuttle!")

    def test_matches_an_exe_whatever_its_quoting(self):
        doc = sa.loads(file_bytes(entry_bytes(5, "Scuttle", EXE)))
        appid, _ = sa.upsert(doc, "Scuttle", EXE)
        self.assertEqual(appid, 5)

    def test_a_new_game_is_added_after_the_others(self):
        appid, changed = sa.upsert(self.doc, "Klaxon", "/home/deck/Games/Klaxon/launch.sh")
        self.assertTrue(changed)
        entry = self.doc["shortcuts"]["1"]
        self.assertEqual(entry["AppName"], "Klaxon")
        self.assertEqual(entry["Exe"], '"/home/deck/Games/Klaxon/launch.sh"')
        self.assertEqual(entry["StartDir"], '"/home/deck/Games/Klaxon"')
        self.assertEqual(entry["appid"], appid)

    def test_a_new_appid_follows_the_usual_convention(self):
        exe = "/home/deck/Games/Klaxon/launch.sh"
        appid, _ = sa.upsert(self.doc, "Klaxon", exe)
        self.assertEqual(appid, zlib.crc32(('"%s"Klaxon' % exe).encode()) | 0x80000000)

    def test_a_new_entry_survives_a_round_trip(self):
        sa.upsert(self.doc, "Klaxon", "/home/deck/Games/Klaxon/launch.sh")
        self.assertEqual(sa.loads(sa.dumps(self.doc)), self.doc)


if __name__ == "__main__":
    unittest.main()
