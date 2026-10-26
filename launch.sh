#!/usr/bin/env bash
# Auto-updating launcher for a game published as GitHub Releases. Steam runs this
# as a non-Steam game. It reads REPO and BINARY from game.conf next to it, fetches
# the newest release if there is one, then starts the game. Offline, or if GitHub
# is unreachable, it just runs whatever build is already here.
set -u

game_folder="$(cd "$(dirname "$0")" && pwd)"
cd "$game_folder"
. ./game.conf

# Downloads $1 to $2, with a progress window when there's a screen to show it on.
# Cancelling the window stops the download. Fails if the download didn't finish.
download() {
	local url="$1" destination="$2"

	if ! command -v zenity > /dev/null || [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
		curl -fsSL --max-time 300 -o "$destination" "$url"
		return
	fi

	# GitHub redirects the download, so take the size from the last response's headers
	local total_bytes
	total_bytes="$(curl -fsSIL --max-time 10 "$url" | tr -d '\r' \
		| awk 'tolower($1) == "content-length:" { size = $2 } END { print size }')"

	curl -fsSL --max-time 300 -o "$destination" "$url" &
	local download_process=$!

	# Write a line every tick, even with nothing new to say, so this loop stops
	# as soon as the window is closed rather than when the download ends.
	{
		while kill -0 "$download_process" 2> /dev/null; do
			if [ -n "$total_bytes" ] && [ "$total_bytes" -gt 0 ] && [ -f "$destination" ]; then
				echo $(( $(wc -c < "$destination") * 100 / total_bytes ))
			else
				echo "# Downloading $latest..."
			fi
			sleep 0.5
		done
		echo 100
	} | zenity --progress --auto-close --title="${BINARY%.*}" --text="Downloading $latest..."
	local window_result=$?

	if [ "$window_result" -ne 0 ] && kill -0 "$download_process" 2> /dev/null; then
		echo "Download cancelled"
		kill "$download_process"
		wait "$download_process" 2> /dev/null
		return 1
	fi
	wait "$download_process"
}

# /releases/latest redirects to /releases/tag/<tag>, which avoids the API and jq
latest="$(curl -fsS --max-time 5 -o /dev/null -w '%{redirect_url}' \
	"https://github.com/$REPO/releases/latest" | sed 's|.*/tag/||')"
current="$(cat version 2> /dev/null)"

if [ -n "$latest" ] && [ "$latest" != "$current" ]; then
	echo "Updating ${current:-nothing} -> $latest"
	if download "https://github.com/$REPO/releases/download/$latest/$BINARY" "$BINARY.download"; then
		chmod +x "$BINARY.download"
		mv "$BINARY.download" "$BINARY"
		echo "$latest" > version
	else
		echo "Download failed, keeping ${current:-no} build"
		rm -f "$BINARY.download"
	fi
fi

if [ ! -x "$BINARY" ]; then
	echo "No build yet - connect to the internet and try again" >&2
	exit 1
fi

exec "./$BINARY" "$@"
