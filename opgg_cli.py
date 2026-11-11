import ast
import json
import os
import re
import sys
from ui import render_banner, render_build, render_help
import requests

URL = "https://mcp-api.op.gg/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
TOOL = "lol_get_champion_analysis"
GAME_MODE = "ranked"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")

FIELDS = [
    "champion",
    "position",
    "data.core_items.{ids_names[],pick_rate,play,win}",
    "data.starter_items.{ids_names[],pick_rate,play,win}",
    "data.boots.{ids_names[],pick_rate,play,win}",
    "data.runes.{primary_page_name,primary_rune_names[],secondary_page_name,secondary_rune_names[],stat_mod_names[],pick_rate,play,win}",
    "data.skills.{order[],pick_rate,play,win}",
    "data.summoner_spells.{ids_names[],pick_rate,play,win}",
    "data.summary.average_stats.{pick_rate,win_rate,ban_rate,kda}",
]

# Any of these typed in the command maps to the API's position name.
POSITIONS = {
    "top": "top",
    "jungle": "jungle", "jung": "jungle", "jg": "jungle",
    "mid": "mid", "middle": "mid",
    "support": "support", "sup": "support", "supp": "support",
    "adc": "adc", "bot": "adc", "ad": "adc",
}

SPELLS = {1: "Cleanse", 3: "Exhaust", 4: "Flash", 6: "Ghost", 7: "Heal",
          11: "Smite", 12: "Teleport", 13: "Clarity", 14: "Ignite",
          21: "Barrier", 32: "Mark"}
STAT_MODS = {5001: "Health Scaling", 5002: "Armor", 5003: "Magic Resist",
             5005: "Attack Speed", 5007: "Ability Haste", 5008: "Adaptive Force"}


# ---------- MCP connection ----------

def parse_response(r):
    text = r.text.strip()
    if text.startswith("event:") or text.startswith("data:") or "\ndata:" in text:
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return r.json()


def rpc(method, params=None, msg_id=1, session_id=None):
    h = dict(HEADERS)
    if session_id:
        h["Mcp-Session-Id"] = session_id
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    r = requests.post(URL, headers=h, data=json.dumps(body), timeout=30)
    r.raise_for_status()
    return r.headers.get("Mcp-Session-Id", session_id), parse_response(r)


def open_session():
    sid, init = rpc("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "opgg-cli", "version": "0.1"},
    })
    if "error" in init:
        raise RuntimeError(f"Initialize failed: {init['error']}")
    h = {**HEADERS, "Mcp-Session-Id": sid or ""}
    requests.post(URL, headers=h,
                  data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                  timeout=30)
    return sid


def fetch_build_text(champion, position):
    sid = open_session()
    args = {
        "game_mode": GAME_MODE,
        "champion": champion,
        "position": position,
        "desired_output_fields": FIELDS,
    }
    _, resp = rpc("tools/call", {"name": TOOL, "arguments": args},
                  msg_id=3, session_id=sid)
    if "error" in resp:
        raise RuntimeError(f"Server error: {resp['error']}")
    for block in resp.get("result", {}).get("content", []):
        if block.get("type") == "text":
            return block["text"]
    raise RuntimeError("Server returned no text")


# ---------- Input handling ----------

def normalize_champion(raw):
    cleaned = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    return "_".join(cleaned.split()).upper()


def parse_command(line):
    text = line.strip().lower()
    if "-" in text:
        champ_raw, pos_raw = text.rsplit("-", 1)
    else:
        parts = text.split()
        if len(parts) < 2:
            raise ValueError("Use champion and position, e.g. ahri-mid or ahri mid")
        champ_raw, pos_raw = " ".join(parts[:-1]), parts[-1]

    position = POSITIONS.get(pos_raw.strip())
    if not position:
        raise ValueError(f"Unknown position '{pos_raw.strip()}'. "
                         "Use top, jungle, mid, support, or adc (see help).")
    champion = normalize_champion(champ_raw)
    if not champion:
        raise ValueError("Missing champion name")
    return champion, position


def get_text(champion, position):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{champion.lower()}_{position}.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read(), True
    text = fetch_build_text(champion, position)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text, False


# ---------- Parsing ----------

def parse_schema(text):
    classes = {}
    for line in text.splitlines():
        m = re.match(r"\s*class (\w+): (.+)", line)
        if m:
            classes[m.group(1)] = [f.strip() for f in m.group(2).split(",")]
    return classes


def extract_call(text):
    for line in text.splitlines():
        if line.startswith("LolGetChampionAnalysis("):
            return line.strip()
    raise ValueError("Response did not contain a LolGetChampionAnalysis(...) result")


def to_py(node, classes):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fields = classes.get(node.func.id)
        if fields is None:
            raise ValueError(f"Unknown class in response: {node.func.id}")
        return {f: to_py(a, classes) for f, a in zip(fields, node.args)}
    return ast.literal_eval(node)


def parse_build(text):
    classes = parse_schema(text)
    tree = ast.parse(extract_call(text), mode="eval")
    return to_py(tree.body, classes)


# ---------- Display ----------

def section(d, name):
    return d.get(name) or {}


def win_rate(sec):
    play = sec.get("play") or 0
    win = sec.get("win") or 0
    return f"{win / play * 100:.1f}%" if play else "n/a"


def names(values):
    out = []
    for v in values or []:
        out.append(SPELLS.get(v, str(v)) if isinstance(v, int) else str(v))
    return out


def show(build):
    d = build.get("data", {})
    avg = section(d.get("summary", {}), "average_stats")
    print(f"\n{build.get('champion', '?')} ({build.get('position', '?')}) - ranked")
    print(f"  Win {avg.get('win_rate', 0) * 100:.1f}% | "
          f"Pick {avg.get('pick_rate', 0) * 100:.1f}% | "
          f"Ban {avg.get('ban_rate', 0) * 100:.1f}% | "
          f"KDA {avg.get('kda', 'n/a')}\n")

    core = section(d, "core_items")
    print("Core items:     ", ", ".join(names(core.get("ids_names"))),
          f"(pick {core.get('pick_rate', 0) * 100:.0f}%, win {win_rate(core)})")
    boots = section(d, "boots")
    print("Boots:          ", ", ".join(names(boots.get("ids_names"))),
          f"(pick {boots.get('pick_rate', 0) * 100:.0f}%, win {win_rate(boots)})")
    starter = section(d, "starter_items")
    print("Starter items:  ", ", ".join(names(starter.get("ids_names"))))
    spells = section(d, "summoner_spells")
    print("Summoner spells:", " + ".join(names(spells.get("ids_names"))))

    r = section(d, "runes")
    mods = [STAT_MODS.get(i, str(i)) for i in r.get("stat_mod_names", [])]
    print(f"\nRunes: {r.get('primary_page_name', '?')} "
          f"[{', '.join(r.get('primary_rune_names', []))}]")
    print(f"       {r.get('secondary_page_name', '?')} "
          f"[{', '.join(r.get('secondary_rune_names', []))}]")
    print(f"       Stat shards: {', '.join(mods)} "
          f"(pick {r.get('pick_rate', 0) * 100:.0f}%, win {win_rate(r)})")

    skills = section(d, "skills")
    order = " > ".join(skills.get("order", []))
    print(f"\nSkill order: {order} (win {win_rate(skills)})")


# ---------- Commands ----------

def print_help():
      render_help()


def handle(line):
    try:
        champion, position = parse_command(line)
        text, from_cache = get_text(champion, position)
        build = parse_build(text)
        render_build(build)
        print("\n(loaded from cache)" if from_cache else "\n(fetched from OP.GG)")
    except ValueError as e:
        print("Error:", e)
    except requests.RequestException:
        print("Could not reach the OP.GG server. Check your internet connection.")
    except Exception as e:
        print("Unexpected error:", e)


def interactive():
    render_banner()
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line.lower() in ("help", "h", "?"):
            print_help()
            continue
        handle(line)


def main():
    if len(sys.argv) > 1:
        line = " ".join(sys.argv[1:])
        if line.lower() in ("help", "h", "?"):
            print_help()
        else:
            handle(line)
    else:
        interactive()


if __name__ == "__main__":
    main()