import os
import shutil
import stat
import subprocess
import tempfile
import unittest

LAUNCHER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "launch.sh")

# Stands in for curl. It only knows the three requests the launcher makes:
# "which tag is latest?", "how big is the download?" and the download itself.
FAKE_CURL = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG_FOLDER/curl.log"
[ -n "${FAKE_OFFLINE:-}" ] && exit 7
url="${!#}"
output_file=""
asking_for_redirect=""
asking_for_headers=""
while [ $# -gt 0 ]; do
	case "$1" in
		-o) output_file="$2"; shift ;;
		-w) asking_for_redirect="yes"; shift ;;
		-*I*) asking_for_headers="yes" ;;
	esac
	shift
done
if [ -n "$asking_for_redirect" ]; then
	echo -n "https://github.com/someone/game/releases/tag/$FAKE_LATEST_TAG"
	exit 0
fi
if [ -n "$asking_for_headers" ]; then
	printf 'HTTP/2 302\r\nlocation: https://elsewhere\r\n\r\nHTTP/2 200\r\ncontent-length: 1000\r\n\r\n'
	exit 0
fi
[ -n "${FAKE_DOWNLOAD_FAILS:-}" ] && exit 22
sleep "${FAKE_DOWNLOAD_SECONDS:-0}"
printf '#!/bin/sh\necho "ran %s $*"\n' "$FAKE_LATEST_TAG" > "$output_file"
"""

# Stands in for zenity. Reads the progress it's sent, or cancels straight away.
FAKE_ZENITY = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG_FOLDER/zenity.log"
[ -n "${FAKE_CANCEL:-}" ] && exit 1
cat >> "$FAKE_LOG_FOLDER/zenity-progress.log"
"""

OLD_BUILD = '#!/bin/sh\necho "ran v1 $*"\n'


def write_executable(path, contents):
    with open(path, "w") as file:
        file.write(contents)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class LaunchTest(unittest.TestCase):
    def setUp(self):
        self.temporary_folder = tempfile.TemporaryDirectory()
        root = self.temporary_folder.name
        self.game_folder = os.path.join(root, "Games", "Game")
        self.fakes_folder = os.path.join(root, "fakes")
        self.log_folder = os.path.join(root, "logs")
        for folder in (self.game_folder, self.fakes_folder, self.log_folder):
            os.makedirs(folder)
        write_executable(os.path.join(self.fakes_folder, "curl"), FAKE_CURL)
        write_executable(os.path.join(self.fakes_folder, "zenity"), FAKE_ZENITY)

        shutil.copy(LAUNCHER, self.game_folder)
        with open(os.path.join(self.game_folder, "game.conf"), "w") as file:
            file.write('REPO="someone/game"\nBINARY="Game.x86_64"\n')

        self.environment = dict(os.environ)
        self.environment["PATH"] = self.fakes_folder + os.pathsep + os.environ["PATH"]
        self.environment["FAKE_LOG_FOLDER"] = self.log_folder
        self.environment["FAKE_LATEST_TAG"] = "v2"
        self.environment["DISPLAY"] = ":0"

    def tearDown(self):
        self.temporary_folder.cleanup()

    def have_old_build(self):
        write_executable(os.path.join(self.game_folder, "Game.x86_64"), OLD_BUILD)
        self.write_game_file("version", "v1\n")

    def write_game_file(self, name, contents):
        with open(os.path.join(self.game_folder, name), "w") as file:
            file.write(contents)

    def read_game_file(self, name):
        with open(os.path.join(self.game_folder, name)) as file:
            return file.read()

    def read_log(self, name):
        path = os.path.join(self.log_folder, name)
        if not os.path.exists(path):
            return ""
        with open(path) as file:
            return file.read()

    def launch(self, *arguments):
        # Run from somewhere else, the way Steam does, to check the launcher finds its own folder
        return subprocess.run(["bash", os.path.join(self.game_folder, "launch.sh"), *arguments],
                              cwd=self.temporary_folder.name, env=self.environment,
                              capture_output=True, text=True, timeout=20)

    def test_downloads_a_new_release_then_runs_it(self):
        self.have_old_build()

        result = self.launch("--fullscreen")

        self.assertEqual(result.stdout.strip().splitlines()[-1], "ran v2 --fullscreen")
        self.assertEqual(self.read_game_file("version"), "v2\n")
        self.assertIn("https://github.com/someone/game/releases/download/v2/Game.x86_64",
                      self.read_log("curl.log"))

    def test_a_first_launch_downloads_the_game(self):
        result = self.launch()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "ran v2")

    def test_runs_the_build_it_has_when_already_up_to_date(self):
        self.have_old_build()
        self.environment["FAKE_LATEST_TAG"] = "v1"

        result = self.launch()

        self.assertEqual(result.stdout.strip(), "ran v1")
        self.assertNotIn("/releases/download/", self.read_log("curl.log"))
        self.assertEqual(self.read_log("zenity.log"), "")

    def test_runs_the_build_it_has_when_offline(self):
        self.have_old_build()
        self.environment["FAKE_OFFLINE"] = "yes"

        result = self.launch()

        self.assertEqual(result.stdout.strip(), "ran v1")

    def test_keeps_the_build_it_has_when_the_download_fails(self):
        self.have_old_build()
        self.environment["FAKE_DOWNLOAD_FAILS"] = "yes"

        result = self.launch()

        self.assertEqual(result.stdout.strip().splitlines()[-1], "ran v1")
        self.assertEqual(self.read_game_file("version"), "v1\n")
        self.assertFalse(os.path.exists(os.path.join(self.game_folder, "Game.x86_64.download")))

    def test_cancelling_the_download_runs_the_build_it_has(self):
        self.have_old_build()
        self.environment["FAKE_CANCEL"] = "yes"
        self.environment["FAKE_DOWNLOAD_SECONDS"] = "5"

        result = self.launch()

        self.assertEqual(result.stdout.strip().splitlines()[-1], "ran v1")
        self.assertEqual(self.read_game_file("version"), "v1\n")
        self.assertFalse(os.path.exists(os.path.join(self.game_folder, "Game.x86_64.download")))

    def test_shows_download_progress_ending_at_100(self):
        self.have_old_build()

        self.launch()

        self.assertIn("--progress", self.read_log("zenity.log"))
        self.assertEqual(self.read_log("zenity-progress.log").split()[-1], "100")

    def test_downloads_without_a_window_when_there_is_no_display(self):
        self.have_old_build()
        del self.environment["DISPLAY"]
        self.environment.pop("WAYLAND_DISPLAY", None)

        result = self.launch()

        self.assertEqual(result.stdout.strip().splitlines()[-1], "ran v2")
        self.assertEqual(self.read_log("zenity.log"), "")

    def test_says_so_when_there_is_no_build_and_no_internet(self):
        self.environment["FAKE_OFFLINE"] = "yes"

        result = self.launch()

        self.assertEqual(result.returncode, 1)
        self.assertIn("No build yet", result.stderr)


if __name__ == "__main__":
    unittest.main()
