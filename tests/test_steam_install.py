import os
import stat
import subprocess
import tempfile
import unittest

TOOLS_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEAM_INSTALL = os.path.join(TOOLS_FOLDER, "steam-install")

# Stand in for ssh and scp. Instead of reaching a device, they act on a folder
# that plays the device's home folder.
FAKE_SSH = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG_FOLDER/ssh.log"
[ -n "${FAKE_UNREACHABLE:-}" ] && exit 255
while [ "$1" = "-o" ]; do shift 2; done
shift   # the host
cd "$FAKE_DEVICE_HOME" && HOME="$FAKE_DEVICE_HOME" PATH="$FAKE_DEVICE_PATH" bash -c "$*"
"""

FAKE_SCP = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG_FOLDER/scp.log"
[ -n "${FAKE_UNREACHABLE:-}" ] && exit 255
while [ "${1:0:1}" = "-" ]; do
	if [ "$1" = "-o" ]; then shift; fi
	shift
done
destination="$FAKE_DEVICE_HOME/${!##*:}"
cp "${@:1:$#-1}" "$destination"
"""

# On the device, records how steam_add.py was run instead of touching Steam.
FAKE_DEVICE_PYTHON = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$HOME/python-arguments"
"""


def write_executable(path, contents):
    with open(path, "w") as file:
        file.write(contents)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class SteamInstallTest(unittest.TestCase):
    def setUp(self):
        self.temporary_folder = tempfile.TemporaryDirectory()
        root = self.temporary_folder.name
        self.game_repo = os.path.join(root, "celestial-meadow")
        self.device_home = os.path.join(root, "device-home")
        fakes_folder = os.path.join(root, "fakes")
        device_bin_folder = os.path.join(root, "device-bin")
        self.log_folder = os.path.join(root, "logs")
        for folder in (os.path.join(self.game_repo, "steam", "art"), self.device_home,
                       fakes_folder, device_bin_folder, self.log_folder):
            os.makedirs(folder)

        write_executable(os.path.join(fakes_folder, "ssh"), FAKE_SSH)
        write_executable(os.path.join(fakes_folder, "scp"), FAKE_SCP)
        write_executable(os.path.join(device_bin_folder, "python3"), FAKE_DEVICE_PYTHON)

        self.write_repo_file("steam/game.conf",
                             'NAME="Celestial Meadow"\nREPO="someone/celestial-meadow"\nBINARY="Meadow.x86_64"\n')
        for role in ("cover", "capsule", "hero", "logo", "icon"):
            self.write_repo_file("steam/art/%s.png" % role, "%s picture" % role)

        self.environment = dict(os.environ)
        self.environment["PATH"] = fakes_folder + os.pathsep + os.environ["PATH"]
        self.environment["FAKE_LOG_FOLDER"] = self.log_folder
        self.environment["FAKE_DEVICE_HOME"] = self.device_home
        self.environment["FAKE_DEVICE_PATH"] = device_bin_folder + os.pathsep + "/usr/bin:/bin"

    def tearDown(self):
        self.temporary_folder.cleanup()

    def write_repo_file(self, name, contents):
        with open(os.path.join(self.game_repo, name), "w") as file:
            file.write(contents)

    def read_device_file(self, name):
        with open(os.path.join(self.device_home, name)) as file:
            return file.read()

    def install(self):
        return subprocess.run([STEAM_INSTALL, "steammachine.local", self.game_repo],
                              env=self.environment, capture_output=True, text=True, timeout=20)

    def test_puts_the_launcher_and_its_settings_in_the_games_folder(self):
        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(TOOLS_FOLDER, "launch.sh")) as file:
            self.assertEqual(self.read_device_file("Games/Celestial Meadow/launch.sh"), file.read())
        self.assertTrue(os.access(os.path.join(self.device_home, "Games/Celestial Meadow/launch.sh"), os.X_OK))
        self.assertIn('REPO="someone/celestial-meadow"', self.read_device_file("Games/Celestial Meadow/game.conf"))

    def test_copies_the_art(self):
        self.install()

        for role in ("cover", "capsule", "hero", "logo", "icon"):
            self.assertEqual(self.read_device_file("Games/Celestial Meadow/art/%s.png" % role), "%s picture" % role)

    def test_adds_the_game_to_steam(self):
        self.install()

        arguments = self.read_device_file("python-arguments").splitlines()
        self.assertEqual(arguments, [
            os.path.join(self.device_home, ".local/share/steam-tools/steam_add.py"),
            "Celestial Meadow",
            os.path.join(self.device_home, "Games/Celestial Meadow/launch.sh"),
            os.path.join(self.device_home, "Games/Celestial Meadow/art"),
        ])
        with open(os.path.join(TOOLS_FOLDER, "steam_add.py")) as file:
            self.assertEqual(self.read_device_file(".local/share/steam-tools/steam_add.py"), file.read())

    def test_works_without_art(self):
        for role in ("cover", "capsule", "hero", "logo", "icon"):
            os.remove(os.path.join(self.game_repo, "steam/art/%s.png" % role))
        os.rmdir(os.path.join(self.game_repo, "steam/art"))

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = self.read_device_file("python-arguments").splitlines()
        self.assertEqual(len(arguments), 3)   # no art folder for steam_add

    def test_running_it_again_is_fine(self):
        self.install()
        result = self.install()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_refuses_a_game_conf_missing_a_setting(self):
        self.write_repo_file("steam/game.conf", 'NAME="Celestial Meadow"\nREPO="someone/celestial-meadow"\n')

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BINARY", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.log_folder, "ssh.log")))

    def test_refuses_a_repo_without_a_game_conf(self):
        os.remove(os.path.join(self.game_repo, "steam/game.conf"))

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("steam/game.conf", result.stderr)

    def test_says_so_when_the_device_cant_be_reached(self):
        self.environment["FAKE_UNREACHABLE"] = "yes"

        result = self.install()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("steammachine.local", result.stderr)

    def test_fails_fast_rather_than_asking_for_a_password(self):
        self.install()

        with open(os.path.join(self.log_folder, "ssh.log")) as file:
            self.assertIn("BatchMode=yes", file.read())


if __name__ == "__main__":
    unittest.main()
