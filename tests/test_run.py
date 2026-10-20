import os
import tempfile
import unittest

import steam_add as sa
from tests.test_vdf import SCUTTLE

EXE = "/home/deck/Games/Scuttle/launch.sh"
APPID = 2537009592


class FakeSteam:
    def __init__(self, game_running=False, on_shutdown=None):
        self.calls = []
        self._game_running = game_running
        self._on_shutdown = on_shutdown

    def game_running(self):
        return self._game_running

    def shutdown(self):
        self.calls.append("shutdown")
        if self._on_shutdown:
            self._on_shutdown()

    def wait_until_back(self):
        self.calls.append("back")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.config = os.path.join(root, "userdata", "64662535", "config")
        os.makedirs(os.path.join(self.config, "grid"))
        self.vdf = os.path.join(self.config, "shortcuts.vdf")
        with open(self.vdf, "wb") as f:
            f.write(SCUTTLE)
        self.art = os.path.join(root, "art")
        os.makedirs(self.art)
        self.userdata = os.path.join(root, "userdata")

    def tearDown(self):
        self.tmp.cleanup()

    def add_art(self, role, data=b"png"):
        with open(os.path.join(self.art, role + ".png"), "wb") as f:
            f.write(data)

    def grid(self, name):
        path = os.path.join(self.config, "grid", name)
        return open(path, "rb").read() if os.path.exists(path) else None

    def entry(self):
        return sa.loads(open(self.vdf, "rb").read())["shortcuts"]["0"]

    def run_it(self, steam, name="Scuttle"):
        return sa.run(name, EXE, self.art, self.userdata, steam)

    def test_art_lands_under_the_appid_with_steams_names(self):
        for role in ("cover", "capsule", "hero", "logo", "icon"):
            self.add_art(role, role.encode())
        self.run_it(FakeSteam())
        self.assertEqual(self.grid("%dp.png" % APPID), b"cover")
        self.assertEqual(self.grid("%d.png" % APPID), b"capsule")
        self.assertEqual(self.grid("%d_hero.png" % APPID), b"hero")
        self.assertEqual(self.grid("%d_logo.png" % APPID), b"logo")
        self.assertEqual(self.grid("%d_icon.png" % APPID), b"icon")

    def test_the_shortcut_icon_points_at_the_installed_icon(self):
        self.add_art("icon")
        self.run_it(FakeSteam())
        self.assertEqual(self.entry()["icon"], os.path.join(self.config, "grid", "%d_icon.png" % APPID))

    def test_missing_art_is_skipped(self):
        self.add_art("hero")
        self.run_it(FakeSteam())
        self.assertIsNotNone(self.grid("%d_hero.png" % APPID))
        self.assertIsNone(self.grid("%dp.png" % APPID))

    def test_nothing_to_do_means_no_restart(self):
        self.add_art("icon")
        self.run_it(FakeSteam())
        steam = FakeSteam()
        self.run_it(steam)
        self.assertEqual(steam.calls, [])

    def test_a_shortcut_change_is_written_after_steam_has_shut_down(self):
        # Steam rewrites the file as it exits, so anything written before then is lost.
        def steam_rewrites_on_exit():
            with open(self.vdf, "wb") as f:
                f.write(SCUTTLE)
        steam = FakeSteam(on_shutdown=steam_rewrites_on_exit)
        self.run_it(steam, name="Scuttle!")
        self.assertEqual(steam.calls, ["shutdown", "back"])
        self.assertEqual(self.entry()["AppName"], "Scuttle!")

    def test_a_backup_is_kept_before_writing(self):
        self.run_it(FakeSteam(), name="Scuttle!")
        backups = [f for f in os.listdir(self.config) if f.startswith("shortcuts.vdf.bak-")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(open(os.path.join(self.config, backups[0]), "rb").read(), SCUTTLE)

    def test_new_art_alone_still_restarts_steam_so_it_shows(self):
        self.add_art("icon")
        self.run_it(FakeSteam())
        self.add_art("icon", b"new")
        steam = FakeSteam()
        self.run_it(steam)
        self.assertEqual(steam.calls, ["shutdown", "back"])

    def test_refuses_to_restart_while_a_game_is_running(self):
        steam = FakeSteam(game_running=True)
        with self.assertRaises(SystemExit):
            self.run_it(steam, name="Scuttle!")
        self.assertEqual(steam.calls, [])
        self.assertEqual(self.entry()["AppName"], "Scuttle")


if __name__ == "__main__":
    unittest.main()
