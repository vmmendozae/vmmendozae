"""Genera stats.svg con las estadísticas del perfil, incluyendo repos privados.

Usa el token de GH_TOKEN (necesita permisos `repo` y `read:user`).
Solo dibuja totales: no escribe nombres de repos en la imagen.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from html import escape

TOKEN = os.environ["GH_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "stats.svg"
IGNORED = {"HTML", "CSS", "SCSS", "Shell", "Dockerfile", "Makefile", "PLpgSQL"}

# Paleta cálida, la misma de la tarjeta de racha.
BG, BORDER, TITLE, TEXT, MUTED, ACCENT = "#FEF3C7", "#D6A75C", "#9A3412", "#78350F", "#92400E", "#C2410C"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL: {body['errors']}")
    return body["data"]


def rest(path):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={"Authorization": f"bearer {TOKEN}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers.get("Link", "")


def count_commits(repo, login):
    """Cuenta tus commits en un repo: pide 1 por página y lee la última página."""
    try:
        data, link = rest(f"repos/{repo}/commits?author={login}&per_page=1")
    except urllib.error.HTTPError:
        return 0  # repo vacío o sin acceso
    m = re.search(r'[?&]page=(\d+)>; rel="last"', link)
    return int(m.group(1)) if m else len(data)


def search_count(q):
    return rest(f"search/issues?q={urllib.parse.quote(q)}&per_page=1")[0]["total_count"]


def collect():
    # GitHub no devuelve el detalle de las contribuciones privadas en
    # contributionsCollection (salen como "restricted"), así que se arma a mano:
    # repos en los que contribuiste -> tus commits en cada uno -> lenguajes.
    login = gql("{viewer{login}}")["viewer"]["login"]
    repos, cursor = [], None
    q = """
    query($after:String){
      viewer{
        repositoriesContributedTo(first:100,after:$after,includeUserRepositories:true,
            contributionTypes:[COMMIT,PULL_REQUEST,REPOSITORY]){
          pageInfo{hasNextPage endCursor}
          nodes{
            nameWithOwner isPrivate isFork
            languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}
          }
        }
      }
    }"""
    while True:
        page = gql(q, after=cursor)["viewer"]["repositoriesContributedTo"]
        repos += [r for r in page["nodes"] if not r["isFork"]]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    langs, colors, commits, with_commits = defaultdict(float), {}, 0, []
    for repo in repos:
        n = count_commits(repo["nameWithOwner"], login)
        if not n:
            continue
        commits += n
        with_commits.append(repo)
        edges = [e for e in repo["languages"]["edges"] if e["node"]["name"] not in IGNORED]
        size = sum(e["size"] for e in edges) or 1
        for e in edges:
            langs[e["node"]["name"]] += n * e["size"] / size
            colors[e["node"]["name"]] = e["node"]["color"] or MUTED

    return {
        "commits": commits,
        "prs": search_count(f"author:{login} type:pr"),
        "reviews": search_count(f"reviewed-by:{login} type:pr -author:{login}"),
        "issues": search_count(f"author:{login} type:issue"),
        "repos": len(with_commits),
        "private": sum(1 for r in with_commits if r["isPrivate"]),
        "langs": sorted(langs.items(), key=lambda kv: -kv[1])[:6],
        "colors": colors,
    }


def render(s):
    W, H = 800, 210
    rows = [
        ("Commits", s["commits"]),
        ("Pull requests", s["prs"]),
        ("Revisiones de PR", s["reviews"]),
        ("Issues", s["issues"]),
        ("Repos con commits", f'{s["repos"]} ({s["private"]} privados)'),
    ]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif">',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="6" fill="{BG}" stroke="{BORDER}"/>',
        f'<line x1="400" y1="24" x2="400" y2="{H-24}" stroke="{BORDER}"/>',
        f'<text x="28" y="40" font-size="18" font-weight="700" fill="{TITLE}">Actividad</text>',
    ]
    for i, (label, value) in enumerate(rows):
        y = 74 + i * 26
        out.append(f'<text x="28" y="{y}" font-size="14" fill="{MUTED}">{escape(label)}</text>')
        out.append(f'<text x="372" y="{y}" font-size="14" font-weight="700" fill="{TEXT}" text-anchor="end">{escape(str(value))}</text>')

    out.append(f'<text x="428" y="40" font-size="18" font-weight="700" fill="{TITLE}">Lenguajes</text>')
    total = sum(v for _, v in s["langs"]) or 1
    x, bar_w = 428, 344
    for name, v in s["langs"]:
        w = bar_w * v / total
        out.append(f'<rect x="{x:.1f}" y="58" width="{w:.1f}" height="10" fill="{s["colors"][name]}"/>')
        x += w
    out.append(f'<rect x="428" y="58" width="{bar_w}" height="10" rx="5" fill="none" stroke="{BG}" stroke-width="2"/>')
    for i, (name, v) in enumerate(s["langs"]):
        col, row = i % 2, i // 2
        lx, ly = 428 + col * 176, 96 + row * 30
        out.append(f'<circle cx="{lx+5}" cy="{ly-5}" r="5" fill="{s["colors"][name]}"/>')
        out.append(f'<text x="{lx+16}" y="{ly}" font-size="14" fill="{TEXT}">{escape(name)} '
                   f'<tspan fill="{MUTED}">{100*v/total:.1f}%</tspan></text>')
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out.append(f'<text x="{W-16}" y="{H-12}" font-size="10" fill="{MUTED}" text-anchor="end">'
               f'Incluye repos privados · actualizado {stamp}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    stats = collect()
    with open(OUT, "w") as f:
        f.write(render(stats))
    print({k: v for k, v in stats.items() if k != "colors"})
