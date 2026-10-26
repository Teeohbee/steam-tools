import unittest
import zlib

import steam_add
from tests.test_vdf import SCUTTLE_FILE, shortcut_bytes, shortcuts_file_bytes

SCUTTLE_EXE = "/home/deck/Games/Scuttle/launch.sh"
SCUTTLE_APPID = 2537009592
KLAXON_EXE = "/home/deck/Games/Klaxon/launch.sh"
ICON_PATH = "/home/deck/.local/share/Steam/userdata/1/config/grid/2537009592_icon.png"


class ShortcutTest(unittest.TestCase):
    def setUp(self):
        self.document = steam_add.parse_vdf(SCUTTLE_FILE)

    def test_an_existing_shortcut_keeps_its_appid(self):
        steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE)
        self.assertEqual(steam_add.appid_for(self.document, "Scuttle", SCUTTLE_EXE), SCUTTLE_APPID)
        self.assertEqual(len(self.document["shortcuts"]), 1)

    def test_a_second_run_changes_nothing(self):
        steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE, ICON_PATH)
        bytes_after_first_run = steam_add.serialise_vdf(self.document)

        changed = steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE, ICON_PATH)

        self.assertFalse(changed)
        self.assertEqual(steam_add.serialise_vdf(self.document), bytes_after_first_run)

    def test_a_start_dir_written_another_way_is_not_a_change(self):
        # Scuttle's real shortcut on the Steam Machine has StartDir unquoted, with a trailing slash
        shortcut = self.document["shortcuts"]["0"]
        shortcut["StartDir"] = "/home/deck/Games/Scuttle/"

        changed = steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE)

        self.assertFalse(changed)
        self.assertEqual(shortcut["StartDir"], "/home/deck/Games/Scuttle/")

    def test_renames_a_shortcut_found_by_its_exe(self):
        changed = steam_add.add_or_update_shortcut(self.document, "Scuttle!", SCUTTLE_EXE)
        self.assertTrue(changed)
        self.assertEqual(self.document["shortcuts"]["0"]["AppName"], "Scuttle!")

    def test_finds_an_exe_stored_without_quotes(self):
        document = steam_add.parse_vdf(shortcuts_file_bytes(shortcut_bytes(5, "Scuttle", SCUTTLE_EXE)))
        self.assertEqual(steam_add.appid_for(document, "Scuttle", SCUTTLE_EXE), 5)

    def test_leaves_the_icon_alone_when_none_is_given(self):
        steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE, ICON_PATH)
        steam_add.add_or_update_shortcut(self.document, "Scuttle", SCUTTLE_EXE, icon_path=None)
        self.assertEqual(self.document["shortcuts"]["0"]["icon"], ICON_PATH)

    def test_a_new_game_is_added_after_the_others(self):
        changed = steam_add.add_or_update_shortcut(self.document, "Klaxon", KLAXON_EXE)

        self.assertTrue(changed)
        new_shortcut = self.document["shortcuts"]["1"]
        self.assertEqual(new_shortcut["AppName"], "Klaxon")
        self.assertEqual(new_shortcut["Exe"], '"/home/deck/Games/Klaxon/launch.sh"')
        self.assertEqual(new_shortcut["StartDir"], '"/home/deck/Games/Klaxon"')
        self.assertEqual(new_shortcut["appid"], steam_add.appid_for(self.document, "Klaxon", KLAXON_EXE))

    def test_a_new_appid_follows_the_usual_convention(self):
        expected = zlib.crc32(('"%s"Klaxon' % KLAXON_EXE).encode()) | 0x80000000
        self.assertEqual(steam_add.appid_for(self.document, "Klaxon", KLAXON_EXE), expected)

    def test_a_new_shortcut_survives_a_round_trip(self):
        steam_add.add_or_update_shortcut(self.document, "Klaxon", KLAXON_EXE)
        file_bytes = steam_add.serialise_vdf(self.document)
        self.assertEqual(steam_add.parse_vdf(file_bytes), self.document)


if __name__ == "__main__":
    unittest.main()
