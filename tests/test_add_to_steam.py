import os
import tempfile
import unittest

import steam_add
from tests.test_vdf import SCUTTLE_FILE

SCUTTLE_EXE = "/home/deck/Games/Scuttle/launch.sh"
SCUTTLE_APPID = 2537009592


class FakeSteam:
    """Records what it was asked to do instead of touching a real Steam."""
    def __init__(self, game_running=False, do_while_shutting_down=None):
        self.calls = []
        self._game_running = game_running
        self._do_while_shutting_down = do_while_shutting_down

    def is_game_running(self):
        return self._game_running

    def shut_down(self):
        self.calls.append("shut down")
        if self._do_while_shutting_down:
            self._do_while_shutting_down()

    def wait_until_running_again(self):
        self.calls.append("running again")


class AddToSteamTest(unittest.TestCase):
    def setUp(self):
        self.temporary_folder = tempfile.TemporaryDirectory()
        root = self.temporary_folder.name
        self.config_folder = os.path.join(root, "userdata", "64662535", "config")
        os.makedirs(os.path.join(self.config_folder, "grid"))
        self.shortcuts_file = os.path.join(self.config_folder, "shortcuts.vdf")
        with open(self.shortcuts_file, "wb") as file:
            file.write(SCUTTLE_FILE)
        self.art_folder = os.path.join(root, "art")
        os.makedirs(self.art_folder)
        self.userdata_folder = os.path.join(root, "userdata")

    def tearDown(self):
        self.temporary_folder.cleanup()

    def add_art(self, role, contents=b"png"):
        with open(os.path.join(self.art_folder, role + ".png"), "wb") as file:
            file.write(contents)

    def grid_file(self, name):
        path = os.path.join(self.config_folder, "grid", name)
        return open(path, "rb").read() if os.path.exists(path) else None

    def scuttle_shortcut(self):
        with open(self.shortcuts_file, "rb") as file:
            return steam_add.parse_vdf(file.read())["shortcuts"]["0"]

    def add_scuttle(self, steam, name="Scuttle"):
        steam_add.add_to_steam(name, SCUTTLE_EXE, self.art_folder, self.userdata_folder, steam)

    def test_art_lands_under_the_appid_with_steams_names(self):
        for role in ("cover", "capsule", "hero", "logo", "icon"):
            self.add_art(role, role.encode())
        self.add_scuttle(FakeSteam())
        self.assertEqual(self.grid_file("%dp.png" % SCUTTLE_APPID), b"cover")
        self.assertEqual(self.grid_file("%d.png" % SCUTTLE_APPID), b"capsule")
        self.assertEqual(self.grid_file("%d_hero.png" % SCUTTLE_APPID), b"hero")
        self.assertEqual(self.grid_file("%d_logo.png" % SCUTTLE_APPID), b"logo")
        self.assertEqual(self.grid_file("%d_icon.png" % SCUTTLE_APPID), b"icon")

    def test_the_shortcut_icon_points_at_the_installed_icon(self):
        self.add_art("icon")
        self.add_scuttle(FakeSteam())
        self.assertEqual(self.scuttle_shortcut()["icon"], os.path.join(self.config_folder, "grid", "%d_icon.png" % SCUTTLE_APPID))

    def test_missing_art_is_skipped(self):
        self.add_art("hero")
        self.add_scuttle(FakeSteam())
        self.assertIsNotNone(self.grid_file("%d_hero.png" % SCUTTLE_APPID))
        self.assertIsNone(self.grid_file("%dp.png" % SCUTTLE_APPID))

    def test_nothing_to_do_means_no_restart(self):
        self.add_art("icon")
        self.add_scuttle(FakeSteam())
        steam = FakeSteam()
        self.add_scuttle(steam)
        self.assertEqual(steam.calls, [])

    def test_a_shortcut_change_is_written_after_steam_has_shut_down(self):
        # Steam rewrites the file as it exits, so anything written before then is lost.
        def steam_rewrites_on_exit():
            with open(self.shortcuts_file, "wb") as file:
                file.write(SCUTTLE_FILE)
        steam = FakeSteam(do_while_shutting_down=steam_rewrites_on_exit)
        self.add_scuttle(steam, name="Scuttle!")
        self.assertEqual(steam.calls, ["shut down", "running again"])
        self.assertEqual(self.scuttle_shortcut()["AppName"], "Scuttle!")

    def test_a_backup_is_kept_before_writing(self):
        self.add_scuttle(FakeSteam(), name="Scuttle!")
        backups = [name for name in os.listdir(self.config_folder) if name.startswith("shortcuts.vdf.bak-")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(open(os.path.join(self.config_folder, backups[0]), "rb").read(), SCUTTLE_FILE)

    def test_new_art_alone_still_restarts_steam_so_it_shows(self):
        self.add_art("icon")
        self.add_scuttle(FakeSteam())
        self.add_art("icon", b"new")
        steam = FakeSteam()
        self.add_scuttle(steam)
        self.assertEqual(steam.calls, ["shut down", "running again"])

    def test_refuses_to_restart_while_a_game_is_running(self):
        steam = FakeSteam(game_running=True)
        with self.assertRaises(SystemExit):
            self.add_scuttle(steam, name="Scuttle!")
        self.assertEqual(steam.calls, [])
        self.assertEqual(self.scuttle_shortcut()["AppName"], "Scuttle")

    def test_new_art_refused_while_a_game_is_running_still_shows_on_the_next_run(self):
        self.add_art("icon")
        self.add_scuttle(FakeSteam())
        self.add_art("icon", b"new")

        with self.assertRaises(SystemExit):
            self.add_scuttle(FakeSteam(game_running=True))
        self.assertEqual(self.grid_file("%d_icon.png" % SCUTTLE_APPID), b"png")

        steam = FakeSteam()
        self.add_scuttle(steam)
        self.assertEqual(steam.calls, ["shut down", "running again"])
        self.assertEqual(self.grid_file("%d_icon.png" % SCUTTLE_APPID), b"new")


if __name__ == "__main__":
    unittest.main()
