# steam-tools

Put Godot games built on a Mac into the Steam library on a SteamOS device (Steam Machine, Steam Deck) over SSH, without Desktop Mode.

## steam_add.py (runs on the device)

```sh
python3 steam_add.py "Scuttle" ~/Games/Scuttle/launch.sh ~/scuttle-art
```

Adds the non-Steam shortcut for that launcher, or updates the existing one (matched by exe, so its appid and playtime are kept). It then copies `cover.png`, `capsule.png`, `hero.png`, `logo.png` and `icon.png` from the art folder into `grid/` under Steam's names. Steam restarts only if something changed, and never while a game is running. `shortcuts.vdf` is backed up before every write.

Standard library only.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
