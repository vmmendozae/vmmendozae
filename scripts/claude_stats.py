"""Genera claude.svg con tu uso de Claude Code, leyendo los registros locales.

Claude Code guarda cada sesión en ~/.claude/projects/**/*.jsonl y borra las
viejas (30 días por defecto). Por eso los totales por día se acumulan en
data/claude-usage.json: los días que siguen en los registros se recalculan,
los que ya se borraron se conservan.

Uso: python3 scripts/claude_stats.py [carpeta-del-repo]
"""

import datetime as dt
import glob
import json
import os
import sys
from collections import defaultdict
from html import escape

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.expanduser("~/.claude/projects")
DATA = os.path.join(REPO, "data", "claude-usage.json")
OUT = os.path.join(REPO, "claude.svg")
TZ = dt.timezone(dt.timedelta(hours=-5))  # Colombia

BG, BORDER, TITLE, TEXT, MUTED, ACCENT = "#FEF3C7", "#D6A75C", "#9A3412", "#78350F", "#92400E", "#C2410C"
KINDS = ("input", "output", "cache_write", "cache_read")


def read_logs():
    """Totales por día y por modelo. Cada respuesta se cuenta una vez."""
    seen, days = set(), {}
    for path in glob.glob(os.path.join(LOGS, "**", "*.jsonl"), recursive=True):
        with open(path, errors="ignore") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                msg = e.get("message") or {}
                u, ts = msg.get("usage"), e.get("timestamp")
                if not isinstance(u, dict) or not ts:
                    continue
                key = (msg.get("id"), e.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                model = msg.get("model") or "?"
                if model.startswith("<"):  # respuestas sintéticas, no del modelo
                    continue
                day = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ).date().isoformat()
                d = days.setdefault(day, {"models": defaultdict(lambda: dict.fromkeys(KINDS, 0)), "sessions": set()})
                m = d["models"][model]
                m["input"] += u.get("input_tokens", 0) or 0
                m["output"] += u.get("output_tokens", 0) or 0
                m["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
                m["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                d["sessions"].add(e.get("sessionId"))
    return {day: {"models": dict(d["models"]), "sessions": len(d["sessions"])} for day, d in days.items()}


def merge(history, fresh):
    # Un día que sigue en los registros se recalcula; el de hoy puede crecer.
    for day, d in fresh.items():
        old = history.get(day)
        if not old or total(d) >= total(old):
            history[day] = d
    return dict(sorted(history.items()))


def total(day, kinds=KINDS):
    return sum(m[k] for m in day["models"].values() for k in kinds)


def human(n):
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= size:
            return f"{n/size:.1f}{unit}".replace(".0", "")
    return str(int(n))


def pretty_model(name):
    # claude-opus-5-5 -> Opus 5.5 ; claude-sonnet-4-5-20250929 -> Sonnet 4.5
    parts = [p for p in name.replace("claude-", "").split("-") if not (p.isdigit() and len(p) == 8)]
    words = [p for p in parts if not p.isdigit()]
    nums = [p for p in parts if p.isdigit()]
    return f'{" ".join(w.capitalize() for w in words)} {".".join(nums)}'.strip()


def render(history):
    today = dt.datetime.now(TZ).date()
    month = today.strftime("%Y-%m")
    all_tokens = sum(total(d) for d in history.values())
    month_tokens = sum(total(d) for day, d in history.items() if day.startswith(month))
    output_tokens = sum(total(d, ("output",)) for d in history.values())
    active_days = len(history)
    sessions = sum(d["sessions"] for d in history.values())
    by_model = defaultdict(int)
    for d in history.values():
        for name, m in d["models"].items():
            by_model[pretty_model(name)] += sum(m.values())
    top = sorted(by_model.items(), key=lambda kv: -kv[1])[:4]
    since = dt.date.fromisoformat(min(history)).strftime("%d/%m/%Y") if history else "-"

    W, H = 800, 210
    rows = [
        ("Tokens totales", human(all_tokens)),
        ("Tokens este mes", human(month_tokens)),
        ("Tokens generados por Claude", human(output_tokens)),
        ("Días con Claude Code", active_days),
        ("Sesiones", sessions),
    ]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif">',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="6" fill="{BG}" stroke="{BORDER}"/>',
        f'<line x1="400" y1="24" x2="400" y2="{H-24}" stroke="{BORDER}"/>',
        f'<text x="28" y="40" font-size="18" font-weight="700" fill="{TITLE}">Claude Code</text>',
    ]
    for i, (label, value) in enumerate(rows):
        y = 74 + i * 26
        out.append(f'<text x="28" y="{y}" font-size="14" fill="{MUTED}">{escape(label)}</text>')
        out.append(f'<text x="372" y="{y}" font-size="14" font-weight="700" fill="{TEXT}" text-anchor="end">{escape(str(value))}</text>')

    out.append(f'<text x="428" y="40" font-size="18" font-weight="700" fill="{TITLE}">Modelos</text>')
    biggest = top[0][1] if top else 1
    for i, (name, n) in enumerate(top):
        y = 70 + i * 30
        w = 200 * n / biggest
        out.append(f'<text x="428" y="{y+11}" font-size="14" fill="{TEXT}">{escape(name)}</text>')
        out.append(f'<rect x="540" y="{y}" width="{w:.1f}" height="14" rx="3" fill="{ACCENT}" opacity="{1 - i*0.18:.2f}"/>')
        out.append(f'<text x="{548 + w:.1f}" y="{y+11}" font-size="13" fill="{MUTED}">{human(n)}</text>')
    out.append(f'<text x="{W-16}" y="{H-12}" font-size="10" fill="{MUTED}" text-anchor="end">'
               f'Desde {since} · tokens de entrada, salida y caché · actualizado {today.isoformat()}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    history = {}
    if os.path.exists(DATA):
        with open(DATA) as f:
            history = json.load(f)
    history = merge(history, read_logs())
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w") as f:
        json.dump(history, f, indent=1)
    with open(OUT, "w") as f:
        f.write(render(history))
    print(f"{len(history)} días · {human(sum(total(d) for d in history.values()))} tokens")
