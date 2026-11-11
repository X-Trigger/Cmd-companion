import os

if os.name == "nt":
    os.system("")  # turns on ANSI colors in Windows terminals

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
PURPLE = "\033[38;5;141m"
GOLD = "\033[38;5;221m"
BLUE = "\033[38;5;117m"
GREEN = "\033[38;5;114m"
RED = "\033[38;5;203m"
GREY = "\033[38;5;245m"
WHITE = "\033[38;5;255m"
WIDTH = 60

SPELLS = {1: "Cleanse", 3: "Exhaust", 4: "Flash", 6: "Ghost", 7: "Heal",
          11: "Smite", 12: "Teleport", 13: "Clarity", 14: "Ignite",
          21: "Barrier", 32: "Mark"}
STAT_MODS = {5001: "Health", 5002: "Armor", 5003: "Magic Resist",
             5005: "Attack Speed", 5007: "Ability Haste", 5008: "Adaptive Force"}


def paint(text, *styles):
    return "".join(styles) + str(text) + RESET


def rule(ch="─"):
    return paint(ch * WIDTH, GREY)


def header(text):
    return f"\n{paint('◆ ' + text.upper(), BOLD, PURPLE)}\n{rule()}"


def to_pct(x):
    return float(x or 0) * 100


def win_pct(sec):
    play = sec.get("play") or 0
    win = sec.get("win") or 0
    return win / play * 100 if play else None


def rate_color(v):
    return GREEN if v >= 50 else RED


def bar(percent, width=20):
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    return paint("█" * filled, rate_color(percent)) + paint("░" * (width - filled), GREY)


def name_of(v, table):
    try:
        return table.get(int(v), str(v))
    except (TypeError, ValueError):
        return str(v)


def join(values):
    return " · ".join(str(v) for v in values)


def render_banner():
    print(paint("╭" + "─" * (WIDTH - 2) + "╮", PURPLE))
    print(paint("│", PURPLE) + paint("OP.GG Build Lookup".center(WIDTH - 2), BOLD, WHITE) + paint("│", PURPLE))
    print(paint("│", PURPLE) + paint("help for commands · exit to quit".center(WIDTH - 2), DIM) + paint("│", PURPLE))
    print(paint("╰" + "─" * (WIDTH - 2) + "╯", PURPLE))


def item_row(label, sec):
    names = sec.get("ids_names") or []
    if not names:
        return f"  {paint(label.ljust(10), GREY)}{paint('—', GREY)}"
    pick = to_pct(sec.get("pick_rate"))
    w = win_pct(sec)
    stats = f"pick {pick:.0f}%" + (f" · win {w:.0f}%" if w is not None else "")
    return (f"  {paint(label.ljust(10), GREY)}{paint(join(names), WHITE)}\n"
            f"  {' ' * 10}{paint(stats, DIM)}")


def rune_block(r, index=None):
    tag = paint(f"[{index}] ", BOLD, GOLD) if index else "    "
    primary = paint(r.get("primary_page_name", "?"), BOLD, PURPLE)
    prim_runes = paint(join(r.get("primary_rune_names", [])), WHITE)
    secondary = paint(r.get("secondary_page_name", "?"), BOLD, BLUE)
    sec_runes = paint(join(r.get("secondary_rune_names", [])), WHITE)
    shards = paint(" · ".join(name_of(s, STAT_MODS) for s in r.get("stat_mod_names", [])), GREY)
    w = win_pct(r)
    stats_txt = f"pick {to_pct(r.get('pick_rate')):.0f}%" + (f" · win {w:.0f}%" if w is not None else "")
    return (f"  {tag}{primary}  {prim_runes}\n"
            f"       {secondary}  {sec_runes}\n"
            f"       {shards}   {paint(stats_txt, DIM)}")


def render_build(build):
    d = build.get("data", {})
    champ = str(build.get("champion", "?")).replace("_", " ").title()
    pos = str(build.get("position", "?")).upper()
    avg = d.get("summary", {}).get("average_stats", {})
    wr = to_pct(avg.get("win_rate"))
    pick = to_pct(avg.get("pick_rate"))
    ban = to_pct(avg.get("ban_rate"))
    kda = avg.get("kda", "n/a")

    print()
    print(f" {paint(champ, BOLD, WHITE)}  {paint(pos + ' · Ranked', GREY)}")
    print(rule("━"))
    print(f"  Win    {paint(f'{wr:.1f}%', BOLD, rate_color(wr))}  {bar(wr)}")
    print(f"  Pick   {paint(f'{pick:.1f}%', GOLD)}    Ban {paint(f'{ban:.1f}%', GOLD)}    "
          f"KDA {paint(kda, BLUE)}")

    print(header("Items"))
    print(item_row("Starter", d.get("starter_items", {})))
    print(item_row("Core", d.get("core_items", {})))
    print(item_row("Boots", d.get("boots", {})))

    spells = d.get("summoner_spells", {}).get("ids_names") or []
    spell_text = " + ".join(name_of(s, SPELLS) for s in spells) or "—"
    print(header("Summoner spells"))
    print(f"  {paint(spell_text, WHITE)}")

    print(header("Runes"))
    print(rune_block(d.get("runes", {})))

    skills = d.get("skills", {})
    order = skills.get("order") or []
    print(header("Skill order"))
    print("  " + " ".join(paint(k, BOLD, GOLD) for k in order))
    w = win_pct(skills)
    if w is not None:
        print(f"  {paint(f'win {w:.1f}%', DIM)}")
    print(rule("━"))


def render_runes(options):
    print(header("Rune setups"))
    for i, r in enumerate(options, 1):
        print(rune_block(r, index=i))
        print()
    if len(options) == 1:
        print(paint("  Only one setup is available from OP.GG for this champion.", DIM))


def render_help():
    print(header("Usage"))
    for example in ["ahri-mid", "ahri mid", "miss fortune-bot", "dr mundo-top"]:
        print(f"  {paint('›', PURPLE)} {paint(example, BOLD, GOLD)}")

    print(header("Lanes (any letter case)"))
    for name, alias in [("top", ""), ("jungle", "jung, jg"), ("mid", "middle"),
                        ("support", "sup"), ("adc", "bot, ad")]:
        print(f"  {paint(name.ljust(10), BOLD, WHITE)}{paint(alias, GREY)}")

    print(header("Commands"))
    print(f"  {paint('help'.ljust(10), BOLD, WHITE)}show this screen")
    print(f"  {paint('exit'.ljust(10), BOLD, WHITE)}quit")
    print(paint("\n  Results are cached, so repeat lookups are instant.", DIM))