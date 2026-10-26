# steam-tools

Put Godot games built on a Mac into the Steam library on a SteamOS device (Steam Machine, Steam Deck) over SSH, without Desktop Mode.

## steam-install (runs on the Mac)

```sh
./steam-install steammachine.local ~/Projects/scuttle
```

Reads the game repo's `steam/game.conf` and copies the launcher, `game.conf` and `steam/art/*.png` to `~/Games/<NAME>/` on the device. It then runs `steam_add.py` there to add the game to Steam. Run it again to refresh the art or the launcher. The game downloads itself on first launch.

```sh
NAME="Scuttle"            # Steam title and folder name; changing it later makes a new shortcut
REPO="Teeohbee/scuttle"   # public GitHub repo with Linux builds as releases
BINARY="Scuttle.x86_64"   # the release asset to download and run
```

## steam_add.py (runs on the device)

```sh
python3 steam_add.py "Scuttle" ~/Games/Scuttle/launch.sh ~/scuttle-art
```

Adds the non-Steam shortcut for that launcher, or updates the existing one (matched by exe, so its appid and playtime are kept). It then copies `cover.png`, `capsule.png`, `hero.png`, `logo.png` and `icon.png` from the art folder into `grid/` under Steam's names. Steam restarts only if something changed, and never while a game is running. `shortcuts.vdf` is backed up before every write.

Standard library only.

## launch.sh (runs on the device)

The game's launcher, and what Steam actually runs. `steam-install` puts a copy at `~/Games/<NAME>/launch.sh`, next to the game's `game.conf`. On every launch it checks GitHub for a newer release, downloads it with a progress window (cancelling keeps the build it has), then starts the game. Offline, it runs whatever build is already there.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
