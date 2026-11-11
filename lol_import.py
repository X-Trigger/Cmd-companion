import json
import os
import sys

import requests
import urllib3
from requests.auth import HTTPBasicAuth

from opgg_cli import BASE_DIR, CACHE_DIR, get_text, parse_build, parse_command

# The client uses a self-signed certificate on localhost, so skip the warning.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOCKFILE_PATHS = [
    r"D:\New folder\Riot Games\League of Legends\lockfile",
    r"C:\Riot Games\League of Legends\lockfile",
]
PAGE_PREFIX = "OPGG "

# Stat shard IDs (OP.GG returns these as numbers)
SHARD_NAMES = {
    5001: "Health Scaling", 5002: "Armor", 5003: "Magic Resist",
    5005: "Attack Speed", 5007: "Ability Haste", 5008: "Adaptive Force",
}


# ---------- Client connection ----------

def read_lockfile():
    for path in LOCKFILE_PATHS:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                parts = f.read().strip().split(":")
            return {"port": parts[2], "password": parts[3]}
    raise RuntimeError("Lockfile not found. Make sure the League Client is open, "
                       "or add its install path to LOCKFILE_PATHS.")


class ClientAPI:
    def __init__(self):
        lf = read_lockfile()
        self.base = f"https://127.0.0.1:{lf['port']}"
        self.auth = HTTPBasicAuth("riot", lf["password"])

    def call(self, method, path, body=None):
        r = requests.request(method, self.base + path, auth=self.auth,
                             json=body, verify=False, timeout=10)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed: {r.status_code} {r.text}")
        return r.json() if r.text else None


# ---------- Data Dragon (name -> ID) ----------

def latest_version():
    r = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=20)
    r.raise_for_status()
    return r.json()[0]


def load_rune_data():
    version = latest_version()
    path = os.path.join(CACHE_DIR, "ddragon_runes.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("version") == version:
            return cached["trees"]

    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    trees = r.json()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": version, "trees": trees}, f)
    return trees


def build_maps(trees):
    style_ids = {}   # "Domination" -> 8100
    perk_ids = {}    # "electrocute" -> 8112
    for tree in trees:
        style_ids[tree["name"].lower()] = tree["id"]
        for slot in tree["slots"]:
            for rune in slot["runes"]:
                perk_ids[rune["name"].lower()] = rune["id"]
    return style_ids, perk_ids


# ---------- Rune page ----------

def resolve(name, table, kind):
    key = str(name).lower()
    if key not in table:
        raise RuntimeError(f"No {kind} ID found for '{name}'. The name may differ "
                           "from Data Dragon's spelling.")
    return table[key]


def build_rune_payload(build, style_ids, perk_ids):
    runes = build["data"]["runes"]
    primary = resolve(runes["primary_page_name"], style_ids, "style")
    secondary = resolve(runes["secondary_page_name"], style_ids, "style")

    primary_ids = [resolve(n, perk_ids, "rune") for n in runes["primary_rune_names"]]
    secondary_ids = [resolve(n, perk_ids, "rune") for n in runes["secondary_rune_names"]]
    shard_ids = [int(s) for s in runes["stat_mod_names"]]

    if len(primary_ids) != 4 or len(secondary_ids) != 2 or len(shard_ids) != 3:
        raise RuntimeError(f"Unexpected rune counts: {len(primary_ids)} primary, "
                           f"{len(secondary_ids)} secondary, {len(shard_ids)} shards")

    return {
        "primaryStyleId": primary,
        "subStyleId": secondary,
        "selectedPerkIds": primary_ids + secondary_ids + shard_ids,
    }


def import_runes(build, champion, position):
    trees = load_rune_data()
    style_ids, perk_ids = build_maps(trees)
    payload = build_rune_payload(build, style_ids, perk_ids)

    client = ClientAPI()

    # Remove older OP.GG pages so the rune page limit isn't reached.
    for page in client.call("GET", "/lol-perks/v1/pages") or []:
        if page.get("name", "").startswith(PAGE_PREFIX) and page.get("isDeletable", True):
            client.call("DELETE", f"/lol-perks/v1/pages/{page['id']}")

    name = f"{PAGE_PREFIX}{champion.replace('_', ' ').title()} {position}"
    body = {"name": name, "current": True, **payload}
    client.call("POST", "/lol-perks/v1/pages", body)
    print(f"Created rune page '{name}'.")


# ---------- Main ----------

def main():
    line = " ".join(sys.argv[1:]) or input("Build to import (e.g. ahri-mid): ")
    champion, position = parse_command(line)
    text, from_cache = get_text(champion, position)
    build = parse_build(text)
    print(f"Importing {champion} ({position})...")
    import_runes(build, champion, position)


if __name__ == "__main__":
    main()