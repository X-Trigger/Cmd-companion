import copy
import sys
import time

import requests

from opgg_cli import get_text, normalize_champion, parse_build
from lol_import import ClientAPI, import_runes, latest_version
from ui import render_build

try:
    import msvcrt
except ImportError:
    msvcrt = None

POLL_SECONDS = 0.5

LCU_POSITION = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "mid",
    "BOTTOM": "adc",
    "UTILITY": "support",
}
LANE_CHOICES = {"top", "jungle", "mid", "adc", "support"}


def load_champion_names():
    version = latest_version()
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return {int(c["key"]): c["name"] for c in r.json()["data"].values()}


def get_session(client):
    try:
        return client.call("GET", "/lol-champ-select/v1/session")
    except RuntimeError:
        return None


def find_hovered(session):
    me = session.get("localPlayerCellId")
    champion_id = None

    for group in session.get("actions", []):
        for action in group:
            if (action.get("actorCellId") == me
                    and action.get("type") == "pick"
                    and not action.get("completed")):
                champion_id = action.get("championId", 0) or 0

    lane = ""
    for member in session.get("myTeam", []):
        if member.get("cellId") == me:
            lane = member.get("assignedPosition", "") or ""
            if champion_id is None:
                champion_id = member.get("championId", 0) or 0
            break

    return champion_id or 0, lane


def check_key():
    """Return the lowercase character of a pressed key, or None. Never blocks."""
    if msvcrt and msvcrt.kbhit():
        return msvcrt.getwch().lower()
    return None


def ask_lane_once():
    while True:
        answer = input("Your lane (practice tool has none assigned): ").strip().lower()
        if answer in LANE_CHOICES:
            return answer
        print("Please type one of: top, jungle, mid, adc, support")


def rune_options(build):
    """Return a list of rune setups. Uses a list if the server gives one, else wraps the single set."""
    runes = build["data"].get("runes")
    if isinstance(runes, list):
        return [r for r in runes if r]
    return [runes] if runes else []


def build_with_runes(build, runes):
    """Copy the build and swap in one rune setup, so lol_import.py needs no changes."""
    new = copy.deepcopy(build)
    new["data"]["runes"] = runes
    return new


def main():
    if msvcrt is None:
        sys.exit("This watcher needs Windows (msvcrt) for non-blocking key input.")

    names = load_champion_names()
    print("Watching champion select. Press Ctrl+C to stop.")

    client = None
    last_status = None
    last_key = None
    current_build = None
    current_options = []
    pending = False
    declined = set()
    custom_lane = None

    while True:
        try:
            if client is None:
                client = ClientAPI()
            session = get_session(client)
        except (RuntimeError, requests.RequestException):
            client = None
            session = None

        if session is None:
            status = "Waiting for the League Client (open it and log in)..."
            if status != last_status:
                print(status)
                last_status = status
            last_key, pending = None, False
            time.sleep(POLL_SECONDS)
            continue

        champion_id, lane = find_hovered(session)

        if champion_id not in names:
            status = "Nothing hovered"
            if status != last_status:
                print(status)
                last_status = status
            last_key, pending = None, False
            time.sleep(POLL_SECONDS)
            continue

        champion = names[champion_id]
        champ_key = normalize_champion(champion)

        if lane:
            position = LCU_POSITION.get(lane)
        else:
            if custom_lane is None:
                custom_lane = ask_lane_once()
            position = custom_lane

        key = (champ_key, position)
        if key != last_key:
            last_key = key
            pending = False
            current_build = None
            current_options = []
            last_status = None
            print(f"\nHovering {champion} ({position})")
            try:
                text, _ = get_text(champ_key, position)
                build = parse_build(text)
            except Exception as e:
                print(f"Could not load build for {champion} ({position}): {e}")
                build = None

            if build is None:
                pass
            else:
                current_build = build
                current_options = rune_options(build)
                render_build(build)
                if not current_options:
                    print("No rune setup in the build data.")
                elif key in declined:
                    print("Skipped earlier for this champion. Hover another or restart to see it again.")
                else:
                    pending = True
                    keys = "1" if len(current_options) == 1 else f"1–{len(current_options)}"
                    print(f"\nPress {keys} to import that setup, N to skip.")

        if pending:
            ch = check_key()
            if ch and ch.isdigit() and 1 <= int(ch) <= len(current_options):
                choice = current_options[int(ch) - 1]
                pending = False
                try:
                    import_runes(build_with_runes(current_build, choice), champ_key, position)
                except Exception as e:
                    print("Import failed:", e)
                print("\nWatching champion select...")
            elif ch == "n":
                pending = False
                declined.add(key)
                print("Skipped.")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")