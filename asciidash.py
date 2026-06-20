#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asciidash — configurable ASCII system / info dashboard.

Shows a big ASCII clock, date, CPU / RAM / disk load, uptime, host info,
weather and a few extras in bordered widgets. Everything is configurable via
~/.config/asciidash/config.json (themes, widgets, layout, units, ...).

Usage:
    python3 dash.py                 # live TUI (q quit, t theme, r refresh)
    python3 dash.py --once          # render once to stdout (for screenshots)
    python3 dash.py --theme matrix --interval 1
    python3 dash.py --list-themes
    python3 dash.py --reset-config
"""
import os
import sys
import time
import json
import socket
import getpass
import platform
import calendar
import argparse
import datetime
import shutil
import urllib.request
import urllib.parse

HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")),
    "asciidash",
)
CFG_PATH = os.path.join(CFG_DIR, "config.json")

# ===================== Конфиг =====================

DEFAULT_CONFIG = {
    "theme": "arch",
    "refresh": 1.0,
    "time_format": "24h",       # "24h" | "12h"
    "show_seconds": True,
    "weather": {
        "enabled": True,
        "location": "Kyiv",
        "units": "metric",      # "metric" | "imperial"
        "refresh_sec": 600,
        "offline_demo": {
            "cond": "Partly cloudy",
            "temp": "+18°C",
            "feels": "+17°C",
            "humidity": "60%",
            "wind": "→ 12 km/h",
        },
    },
    "layout": {
        "top": ["clock"],
        "columns": [
            ["weather", "cpu", "memory", "disk"],
            ["host", "calendar", "quote"],
        ],
    },
    "quotes": [
        "Talk is cheap. Show me the code. — Linus Torvalds",
        "There are only two hard things in CS: cache invalidation and naming things.",
        "It works on my machine. — Every developer ever",
        "Simplicity is the soul of efficiency. — Austin Freeman",
        "First, solve the problem. Then, write the code. — John Johnson",
        "Premature optimization is the root of all evil. — Donald Knuth",
        "I use Arch btw.",
    ],
}


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            cfg = deep_merge(cfg, user)
        except Exception:
            pass
    return cfg


def save_config(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def ensure_config():
    if not os.path.exists(CFG_PATH):
        save_config(DEFAULT_CONFIG)


# ===================== Цвета / темы =====================
# name -> (ansi_sgr, curses_color_name, attr)
COLOR_DEFS = {
    "white":          ("0;37", "white",   "normal"),
    "bright_white":   ("1;37", "white",   "bold"),
    "gray":           ("0;90", "white",   "dim"),
    "cyan":           ("0;36", "cyan",    "normal"),
    "bright_cyan":    ("1;36", "cyan",    "bold"),
    "blue":           ("0;34", "blue",    "normal"),
    "bright_blue":    ("1;34", "blue",    "bold"),
    "green":          ("0;32", "green",   "normal"),
    "bright_green":   ("1;32", "green",   "bold"),
    "yellow":         ("0;33", "yellow",  "normal"),
    "bright_yellow":  ("1;33", "yellow",  "bold"),
    "red":            ("0;31", "red",     "normal"),
    "bright_red":     ("1;31", "red",     "bold"),
    "magenta":        ("0;35", "magenta", "normal"),
    "bright_magenta": ("1;35", "magenta", "bold"),
}

THEMES = {
    "arch": {"accent": "bright_cyan", "border": "blue", "title": "bright_cyan",
             "label": "gray", "value": "bright_white", "good": "bright_green",
             "warn": "bright_yellow", "bad": "bright_red", "dim": "gray"},
    "matrix": {"accent": "bright_green", "border": "green", "title": "bright_green",
               "label": "green", "value": "bright_green", "good": "bright_green",
               "warn": "yellow", "bad": "bright_red", "dim": "green"},
    "amber": {"accent": "bright_yellow", "border": "yellow", "title": "bright_yellow",
              "label": "gray", "value": "bright_yellow", "good": "bright_green",
              "warn": "yellow", "bad": "bright_red", "dim": "gray"},
    "nord": {"accent": "bright_cyan", "border": "bright_blue", "title": "bright_white",
             "label": "gray", "value": "bright_white", "good": "bright_green",
             "warn": "bright_yellow", "bad": "bright_red", "dim": "gray"},
    "mono": {"accent": "bright_white", "border": "gray", "title": "bright_white",
             "label": "gray", "value": "white", "good": "white",
             "warn": "white", "bad": "white", "dim": "gray"},
}

NO_COLOR = False


def resolve_role(theme, role):
    if role is None:
        return None
    return theme.get(role, "value")


def ansi_for(theme, role):
    if NO_COLOR or role is None:
        return "\x1b[0m"
    cname = resolve_role(theme, role)
    sgr = COLOR_DEFS.get(cname, COLOR_DEFS["white"])[0]
    return "\x1b[" + sgr + "m"


# ===================== Большой шрифт (часы) =====================
FONT = {
    "0": ["████", "█  █", "█  █", "█  █", "████"],
    "1": ["  █ ", " ██ ", "  █ ", "  █ ", " ███"],
    "2": ["████", "   █", "████", "█   ", "████"],
    "3": ["████", "   █", "████", "   █", "████"],
    "4": ["█  █", "█  █", "████", "   █", "   █"],
    "5": ["████", "█   ", "████", "   █", "████"],
    "6": ["████", "█   ", "████", "█  █", "████"],
    "7": ["████", "   █", "  █ ", " █  ", " █  "],
    "8": ["████", "█  █", "████", "█  █", "████"],
    "9": ["████", "█  █", "████", "   █", "████"],
    ":": ["  ", "██", "  ", "██", "  "],
    " ": ["  ", "  ", "  ", "  ", "  "],
}


def big_text(s):
    rows = ["", "", "", "", ""]
    for ch in s:
        g = FONT.get(ch, FONT[" "])
        for i in range(5):
            rows[i] += g[i] + " "
    return [r[:-1] for r in rows]


# ===================== Холст =====================
BOX = {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"}


class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.ch = [[" "] * w for _ in range(h)]
        self.rl = [[None] * w for _ in range(h)]

    def put(self, y, x, text, role=None):
        if y < 0 or y >= self.h:
            return
        for i, c in enumerate(text):
            xx = x + i
            if 0 <= xx < self.w:
                self.ch[y][xx] = c
                self.rl[y][xx] = role

    def box(self, y, x, h, w, role, title=None, title_role=None):
        if w < 2 or h < 2:
            return
        self.put(y, x, BOX["tl"] + BOX["h"] * (w - 2) + BOX["tr"], role)
        for yy in range(y + 1, y + h - 1):
            self.put(yy, x, BOX["v"], role)
            self.put(yy, x + w - 1, BOX["v"], role)
        self.put(y + h - 1, x, BOX["bl"] + BOX["h"] * (w - 2) + BOX["br"], role)
        if title:
            self.put(y, x + 2, " " + title + " ", title_role or role)


def normalize_line(line):
    if isinstance(line, str):
        return [(line, "value")]
    out = []
    for seg in line:
        if isinstance(seg, str):
            out.append((seg, "value"))
        else:
            out.append((seg[0], seg[1]))
    return out


def seg_len(line):
    return sum(len(t) for t, _ in normalize_line(line))


def draw_widget(cv, y, x, h, w, title, seglines):
    cv.box(y, x, h, w, "border", title, "title")
    for i, line in enumerate(seglines):
        yy = y + 1 + i
        if yy >= y + h - 1:
            break
        xx = x + 2
        for text, role in normalize_line(line):
            cv.put(yy, xx, text, role)
            xx += len(text)


# ===================== Системные метрики =====================

def read_loadavg():
    try:
        with open("/proc/loadavg") as f:
            p = f.read().split()
        return float(p[0]), float(p[1]), float(p[2])
    except Exception:
        try:
            return os.getloadavg()
        except Exception:
            return (0.0, 0.0, 0.0)


def read_meminfo():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])  # kB
    except Exception:
        pass
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - avail)
    return used, total  # kB


def read_uptime():
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


def cpu_samples():
    """Return list of (total, idle) for cpu and each core."""
    out = []
    try:
        with open("/proc/stat") as f:
            for line in f:
                if not line.startswith("cpu"):
                    break
                parts = line.split()
                if len(parts) < 5:
                    continue
                nums = list(map(int, parts[1:]))
                idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
                total = sum(nums)
                out.append((total, idle))
    except Exception:
        pass
    return out  # [overall, core0, core1, ...]


def cpu_percentages(prev, cur):
    res = []
    for i in range(min(len(prev), len(cur))):
        pt, pi = prev[i]
        ct, ci = cur[i]
        dt = ct - pt
        di = ci - pi
        res.append(100.0 * (dt - di) / dt if dt > 0 else 0.0)
    return res


def disk_usage(path="/"):
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        return used, total
    except Exception:
        return 0, 0


def os_pretty():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.system()


def fmt_uptime(sec):
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, _ = divmod(sec, 60)
    if d:
        return "%dd %dh %dm" % (d, h, m)
    if h:
        return "%dh %dm" % (h, m)
    return "%dm" % m


def fmt_bytes_gb(b):
    return b / (1024.0 ** 3)


# ===================== Погода =====================
WEATHER_ICONS = {
    "sunny": ["  \\ /  ", " — O — ", "  / \\  "],
    "partly": ["  \\ /  ", " _\\_(  ", "  (___) "],
    "cloudy": ["  .--.  ", " (    ) ", " (____) "],
    "rain":   ["  .--.  ", " (    ) ", "  ' ' ' "],
    "snow":   ["  .--.  ", " (    ) ", "  * * * "],
    "storm":  ["  .--.  ", " (    ) ", "  /_ /_ "],
    "fog":    [" _ _ _  ", " _ _ _  ", " _ _ _  "],
}


def icon_for(cond):
    c = (cond or "").lower()
    if "thunder" in c or "storm" in c:
        return "storm"
    if "snow" in c or "sleet" in c or "blizzard" in c:
        return "snow"
    if "rain" in c or "drizzle" in c or "shower" in c:
        return "rain"
    if "fog" in c or "mist" in c or "haze" in c:
        return "fog"
    if "part" in c:
        return "partly"
    if "cloud" in c or "overcast" in c:
        return "cloudy"
    if "sun" in c or "clear" in c:
        return "sunny"
    return "cloudy"


def fetch_weather(wcfg):
    loc = wcfg.get("location", "")
    flag = "u" if wcfg.get("units") == "imperial" else "m"
    fmt = urllib.parse.quote("%C|%t|%f|%h|%w")
    url = "https://wttr.in/%s?format=%s&%s" % (
        urllib.parse.quote(loc), fmt, flag)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        raw = urllib.request.urlopen(req, timeout=4).read().decode("utf-8").strip()
        cond, temp, feels, hum, wind = (raw.split("|") + [""] * 5)[:5]
        return {"cond": cond, "temp": temp, "feels": feels,
                "humidity": hum, "wind": wind, "live": True}
    except Exception:
        return None


# ===================== Виджеты =====================

def make_bar(frac, width):
    width = max(4, width)
    frac = min(1.0, max(0.0, frac))
    f = min(width, int(round(frac * width)))
    role = "good" if frac < 0.6 else "warn" if frac < 0.85 else "bad"
    return [("[", "dim"), ("█" * f, role),
            ("░" * (width - f), "dim"), ("]", "dim")]


def stat_line(label, frac, value, innerw):
    lab = (label + " ")[:6].ljust(6)
    barw = max(4, innerw - len(lab) - len(value) - 4)
    return [(lab, "label")] + make_bar(frac, barw) + [(" " + value, "value")]


def w_clock(cfg, state, innerw):
    now = datetime.datetime.now()
    fmt = "%H:%M:%S" if cfg["show_seconds"] else "%H:%M"
    if cfg.get("time_format") == "12h":
        fmt = "%I:%M:%S" if cfg["show_seconds"] else "%I:%M"
    tstr = now.strftime(fmt)
    rows = big_text(tstr)
    lines = []
    for r in rows:
        pad = max(0, (innerw - len(r)) // 2)
        lines.append([(" " * pad + r, "accent")])
    wk = now.isocalendar()[1]
    suffix = (" " + now.strftime("%p")) if cfg.get("time_format") == "12h" else ""
    date = now.strftime("%A, %d %B %Y") + suffix + "  ·  week %d" % wk
    pad = max(0, (innerw - len(date)) // 2)
    lines.append([(" " * pad + date, "value")])
    return (None, lines)


def w_cpu(cfg, state, innerw):
    pcts = state.get("cpu_pcts") or []
    lines = []
    if pcts:
        lines.append(stat_line("cpu", pcts[0] / 100.0, "%3.0f%%" % pcts[0], innerw))
        for i, p in enumerate(pcts[1:]):
            lines.append(stat_line("c%d" % i, p / 100.0, "%3.0f%%" % p, innerw))
    else:
        lines.append([("sampling...", "dim")])
    l1, l5, l15 = read_loadavg()
    lines.append([("load   ", "label"),
                  ("%.2f  %.2f  %.2f" % (l1, l5, l15), "value")])
    return ("CPU", lines)


def w_memory(cfg, state, innerw):
    used, total = read_meminfo()
    frac = used / total if total else 0
    val = "%.1f/%.1fG" % (used / 1048576.0, total / 1048576.0)
    return ("MEMORY", [stat_line("ram", frac, val, innerw)])


def w_disk(cfg, state, innerw):
    used, total = disk_usage("/")
    frac = used / total if total else 0
    val = "%.0f/%.0fG" % (fmt_bytes_gb(used), fmt_bytes_gb(total))
    return ("DISK /", [stat_line("disk", frac, val, innerw)])


def w_host(cfg, state, innerw):
    lines = [
        [(getpass.getuser() + "@" + socket.gethostname(), "accent")],
        [("os     ", "label"), (os_pretty(), "value")],
        [("kernel ", "label"), (platform.release(), "value")],
        [("arch   ", "label"), (platform.machine(), "value")],
        [("uptime ", "label"), (fmt_uptime(read_uptime()), "value")],
    ]
    return ("HOST", lines)


def w_weather(cfg, state, innerw):
    wcfg = cfg["weather"]
    data = state.get("weather")
    offline = False
    if not data:
        data = dict(wcfg.get("offline_demo", {}))
        offline = True
    icon = WEATHER_ICONS[icon_for(data.get("cond", ""))]
    temp = data.get("temp", "")
    feels = data.get("feels", "")
    hum = data.get("humidity", "")
    wind = data.get("wind", "")
    lines = [
        [(wcfg.get("location", ""), "accent"),
         ("   " + data.get("cond", ""), "label")],
        [(icon[0], "accent")],
        [(icon[1], "accent"), ("  ", None), (temp, "value"),
         ("  feels " + feels, "label")],
        [(icon[2], "accent"), ("  ", None),
         ("hum " + hum + "  wind " + wind, "label")],
    ]
    if offline:
        lines.append([("(offline demo — no network)", "dim")])
    else:
        lines.append([("live · wttr.in", "good")])
    return ("WEATHER", lines)


def w_calendar(cfg, state, innerw):
    now = datetime.datetime.now()
    y, m, today = now.year, now.month, now.day
    title = "%s %d" % (calendar.month_name[m], y)
    pad = max(0, (innerw - len(title)) // 2)
    lines = [[(" " * pad + title, "accent")],
             [("Mo Tu We Th Fr Sa Su", "label")]]
    for week in calendar.monthcalendar(y, m):
        seg = []
        for d in week:
            if d == 0:
                seg.append(("  ", None))
            elif d == today:
                seg.append(("%2d" % d, "good"))
            else:
                seg.append(("%2d" % d, "value"))
            seg.append((" ", None))
        lines.append(seg)
    return ("CALENDAR", lines)


def wrap_text(text, width):
    width = max(8, width)
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def w_quote(cfg, state, innerw):
    quotes = cfg.get("quotes") or [""]
    idx = datetime.datetime.now().timetuple().tm_yday % len(quotes)
    q = quotes[idx]
    lines = [[(ln, "value")] for ln in wrap_text(q, innerw)]
    return ("QUOTE", lines)


WIDGETS = {
    "clock": w_clock, "cpu": w_cpu, "memory": w_memory, "disk": w_disk,
    "host": w_host, "weather": w_weather, "calendar": w_calendar,
    "quote": w_quote,
}


def render_widget(name, cfg, state, innerw):
    fn = WIDGETS.get(name)
    if not fn:
        return (name, [[("unknown widget", "bad")]])
    try:
        return fn(cfg, state, innerw)
    except Exception as e:
        return (name, [[("error: " + str(e)[:innerw], "bad")]])


# ===================== Компоновка =====================

def draw_dashboard(cv, cfg, state):
    W, H = cv.w, cv.h
    gap = 1
    y = 0
    layout = cfg.get("layout", {})
    for name in layout.get("top", []):
        title, seglines = render_widget(name, cfg, state, W - 4)
        h = len(seglines) + 2
        if y + h > H:
            break
        draw_widget(cv, y, 0, h, W, title, seglines)
        y += h + gap
    cols = layout.get("columns", [])
    if not cols:
        return
    n = len(cols)
    colw = (W - (n - 1) * gap) // n
    for ci, col in enumerate(cols):
        cx = ci * (colw + gap)
        cy = y
        for name in col:
            title, seglines = render_widget(name, cfg, state, colw - 4)
            h = len(seglines) + 2
            if cy + h > H:
                break
            draw_widget(cv, cy, cx, h, colw, title, seglines)
            cy += h + gap


def render_ansi(cv, theme):
    last_row = 0
    for y in range(cv.h):
        if any(c != " " for c in cv.ch[y]):
            last_row = y
    out = []
    for y in range(last_row + 1):
        row, roles = cv.ch[y], cv.rl[y]
        last_col = -1
        for x in range(cv.w):
            if row[x] != " ":
                last_col = x
        line, cur = "", "__none__"
        for x in range(last_col + 1):
            role = roles[x]
            if role != cur:
                line += ansi_for(theme, role)
                cur = role
            line += row[x]
        line += "\x1b[0m"
        out.append(line)
    return "\n".join(out)


# ===================== Сбор метрик =====================

def update_stats(state, sample_sleep=0.0):
    cur = cpu_samples()
    prev = state.get("cpu_prev")
    if prev is None and sample_sleep > 0:
        time.sleep(sample_sleep)
        prev, cur = cur, cpu_samples()
    if prev is not None:
        state["cpu_pcts"] = cpu_percentages(prev, cur)
    state["cpu_prev"] = cur


def maybe_weather(cfg, state, force=False):
    wcfg = cfg["weather"]
    if not wcfg.get("enabled", True):
        state["weather"] = None
        return
    now = time.monotonic()
    due = force or (now - state.get("weather_ts", -1e9)) > wcfg.get("refresh_sec", 600)
    if due:
        state["weather"] = fetch_weather(wcfg)
        state["weather_ts"] = now


# ===================== Режим одного кадра =====================

def run_once(cfg, width=None, height=None):
    theme = THEMES.get(cfg["theme"], THEMES["arch"])
    if width is None:
        width = shutil.get_terminal_size((100, 40)).columns
    if height is None:
        height = 160
    state = {}
    update_stats(state, sample_sleep=0.15)
    maybe_weather(cfg, state, force=True)
    cv = Canvas(width, height)
    draw_dashboard(cv, cfg, state)
    sys.stdout.write(render_ansi(cv, theme) + "\n")
    sys.stdout.flush()


# ===================== Живой TUI =====================

def run_tui(cfg):
    import curses

    CURSES_COLORS = {
        "white": curses.COLOR_WHITE, "cyan": curses.COLOR_CYAN,
        "blue": curses.COLOR_BLUE, "green": curses.COLOR_GREEN,
        "yellow": curses.COLOR_YELLOW, "red": curses.COLOR_RED,
        "magenta": curses.COLOR_MAGENTA,
    }
    roles = ["accent", "border", "title", "label", "value",
             "good", "warn", "bad", "dim"]

    def _main(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        try:
            curses.start_color()
            curses.use_default_colors()
        except Exception:
            pass
        theme_names = list(THEMES.keys())
        if cfg["theme"] not in theme_names:
            cfg["theme"] = "arch"

        def build_pairs():
            theme = THEMES.get(cfg["theme"], THEMES["arch"])
            pairs = {}
            idx = 1
            for role in roles:
                cname = theme.get(role, "value")
                ansi, ccolor, attr = COLOR_DEFS.get(cname, COLOR_DEFS["white"])
                col = CURSES_COLORS.get(ccolor, curses.COLOR_WHITE)
                try:
                    curses.init_pair(idx, col, -1)
                except Exception:
                    pass
                a = 0
                if attr == "bold":
                    a = curses.A_BOLD
                elif attr == "dim":
                    a = curses.A_DIM
                pairs[role] = curses.color_pair(idx) | a
                idx += 1
            return pairs

        pairs = build_pairs()
        state = {}
        update_stats(state)
        last_draw = 0.0
        interval = float(cfg.get("refresh", 1.0))
        while True:
            now = time.monotonic()
            if now - last_draw >= interval:
                update_stats(state)
                maybe_weather(cfg, state)
                H, W = stdscr.getmaxyx()
                cv = Canvas(W, H)
                draw_dashboard(cv, cfg, state)
                stdscr.erase()
                for y in range(min(H, cv.h)):
                    x = 0
                    maxx = min(W, cv.w)
                    while x < maxx:
                        role = cv.rl[y][x]
                        j = x
                        run = ""
                        while j < maxx and cv.rl[y][j] == role:
                            run += cv.ch[y][j]
                            j += 1
                        attr = pairs.get(role, 0) if role else 0
                        try:
                            stdscr.addstr(y, x, run, attr)
                        except curses.error:
                            pass
                        x = j
                stdscr.refresh()
                last_draw = now
            try:
                ch = stdscr.getch()
            except Exception:
                ch = -1
            if ch in (ord("q"), ord("Q"), 27):
                break
            elif ch in (ord("t"), ord("T")):
                i = theme_names.index(cfg["theme"])
                cfg["theme"] = theme_names[(i + 1) % len(theme_names)]
                pairs = build_pairs()
                last_draw = 0
            elif ch in (ord("s"), ord("S")):
                cfg["show_seconds"] = not cfg["show_seconds"]
                last_draw = 0
            elif ch in (ord("r"), ord("R")):
                maybe_weather(cfg, state, force=True)
                last_draw = 0
            time.sleep(0.05)

    curses.wrapper(_main)


# ===================== CLI =====================

def main(argv=None):
    global NO_COLOR
    ap = argparse.ArgumentParser(description="asciidash — ASCII info dashboard")
    ap.add_argument("--once", action="store_true",
                    help="render once to stdout and exit (good for screenshots)")
    ap.add_argument("--theme", help="override theme")
    ap.add_argument("--interval", type=float, help="refresh seconds (live mode)")
    ap.add_argument("--location", help="override weather location")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--width", type=int, help="width for --once")
    ap.add_argument("--height", type=int, help="height for --once")
    ap.add_argument("--config", help="path to config file")
    ap.add_argument("--reset-config", action="store_true")
    ap.add_argument("--list-themes", action="store_true")
    args = ap.parse_args(argv)

    global CFG_PATH
    if args.config:
        CFG_PATH = args.config

    if args.list_themes:
        print("Available themes: " + ", ".join(THEMES.keys()))
        return
    if args.reset_config:
        save_config(DEFAULT_CONFIG)
        print("Wrote default config to %s" % CFG_PATH)
        return

    ensure_config()
    cfg = load_config()
    if args.theme:
        cfg["theme"] = args.theme
    if args.interval:
        cfg["refresh"] = args.interval
    if args.location:
        cfg["weather"]["location"] = args.location
    if args.no_color:
        NO_COLOR = True

    if args.once:
        run_once(cfg, width=args.width, height=args.height)
    else:
        try:
            run_tui(cfg)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
