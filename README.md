# steam-tools

Put Godot games built on a Mac into the Steam library on a SteamOS device (Steam Machine, Steam Deck) over SSH, without Desktop Mode.

## steam_add.py (runs on the device)

```sh
python3 steam_add.py "Scuttle" ~/Games/Scuttle/launch.sh ~/scuttle-art
```

Adds the non-Steam shortcut for that launcher, or updates the existing one (matched by exe, so its appid and playtime are kept). It then copies `cover.png`, `capsule.png`, `hero.png`, `logo.png` and `icon.png` from the art folder into `grid/` under Steam's names. Steam restarts only if something changed, and never while a game is running. `shortcuts.vdf` is backed up before every write.

Standard library only.

## launch.sh (runs on the device)

The game's launcher, and what Steam actually runs. Each game gets its own copy at `~/Games/<Name>/launch.sh` beside a `game.conf`:

```sh
REPO="Teeohbee/scuttle"
BINARY="Scuttle.x86_64"
```

On every launch it checks GitHub for a newer release, downloads it with a progress window (cancelling keeps the build it has), then starts the game. Offline, it runs whatever build is already there.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
