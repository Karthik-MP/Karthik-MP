"""Rebuild README.md's dynamic sections and the SVG cards in assets/.

Run by .github/workflows/build.yml. Everything is generated from the GitHub
GraphQL API (with the workflow's GITHUB_TOKEN) and npm, so the profile does
not depend on third-party image services that get rate-limited.

If a data source fails, the old content is kept, so a bad network day never
blanks the README.
"""

import datetime
import html
import json
import os
import pathlib
import re
import urllib.request

USER = "Karthik-MP"
NPM_PACKAGE = "langgraph-ui-components"
SKIP_REPOS = {USER}
ROOT = pathlib.Path(__file__).parent.resolve()
ASSETS = ROOT / "assets"

# Palette (tokyonight-ish, matches the streak card)
BG = "#1a1b27"
BORDER = "#2a2e45"
TITLE = "#70a5fd"
TEXT = "#c0caf5"
MUTED = "#7f88b0"
ACCENT = "#bf91f3"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                 isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        url
        description
        pushedAt
        isArchived
        stargazerCount
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { name tagName publishedAt url }
        }
      }
    }
  }
}
"""

# Languages that are mostly generated/notebook bulk and distort the chart
IGNORE_LANGS = {"Jupyter Notebook", "HTML", "CSS", "SCSS", "Procfile", "Makefile"}


# ---------------------------------------------------------------- helpers

def fetch_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", f"{USER}-readme-builder")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_user(token):
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    data = fetch_json(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


def replace_chunk(content, marker, chunk, inline=False):
    pattern = re.compile(rf"<!-- {marker} starts -->.*<!-- {marker} ends -->", re.DOTALL)
    if not inline:
        chunk = f"\n{chunk}\n"
    return pattern.sub(lambda _: f"<!-- {marker} starts -->{chunk}<!-- {marker} ends -->", content)


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def day(iso):
    return iso.split("T")[0]


def write_if_changed(path, text):
    path.parent.mkdir(exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def card(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">
<style>
  .t {{ font: 600 18px {FONT}; fill: {TITLE}; }}
  .l {{ font: 400 14px {FONT}; fill: {TEXT}; }}
  .v {{ font: 700 14px {FONT}; fill: {TEXT}; }}
  .m {{ font: 400 11px {FONT}; fill: {MUTED}; }}
  .fade {{ opacity: 0; animation: in .6s ease-out forwards; }}
  @keyframes in {{ to {{ opacity: 1; }} }}
</style>
<rect x="0.5" y="0.5" rx="10" width="{width-1}" height="{height-1}" fill="{BG}" stroke="{BORDER}"/>
<text x="25" y="36" class="t">{esc(title)}</text>
{body}
</svg>
"""


# ---------------------------------------------------------------- cards

ICONS = {
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z",
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "pr": "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354Z",
    "issue": "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z",
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z",
    "people": "M2 5.5a3.5 3.5 0 1 1 5.898 2.549 5.508 5.508 0 0 1 3.034 4.084.75.75 0 1 1-1.482.235 4 4 0 0 0-7.9 0 .75.75 0 0 1-1.482-.236A5.507 5.507 0 0 1 3.102 8.05 3.493 3.493 0 0 1 2 5.5ZM11 4a3.001 3.001 0 0 1 2.22 5.018 5.01 5.01 0 0 1 2.56 3.012.749.749 0 0 1-.885.954.752.752 0 0 1-.549-.514 3.507 3.507 0 0 0-2.522-2.372.75.75 0 0 1-.574-.73v-.352a.75.75 0 0 1 .416-.672A1.5 1.5 0 0 0 11 5.5.75.75 0 0 1 11 4Zm-5.5-.5a2 2 0 1 0-.001 3.999A2 2 0 0 0 5.5 3.5Z",
}


def render_stats(user, repos):
    cal = user["contributionsCollection"]
    rows = [
        ("star", "Total stars", sum(r["stargazerCount"] for r in repos)),
        ("commit", "Commits (past year)", cal["totalCommitContributions"]),
        ("pr", "Pull requests", user["pullRequests"]["totalCount"]),
        ("issue", "Issues", user["issues"]["totalCount"]),
        ("repo", "Public repos", user["repositories"]["totalCount"]),
        ("people", "Followers", user["followers"]["totalCount"]),
    ]
    body = []
    for i, (icon, label, value) in enumerate(rows):
        y = 58 + i * 25
        body.append(
            f'<g class="fade" style="animation-delay:{i*120}ms" transform="translate(25,{y})">'
            f'<path fill="{ACCENT}" d="{ICONS[icon]}"/>'
            f'<text x="26" y="12.5" class="l">{label}</text>'
            f'<text x="215" y="12.5" class="v">{fmt(value)}</text></g>'
        )
    total = cal["contributionCalendar"]["totalContributions"]
    ring = f"""
<g transform="translate(360,112)">
  <circle r="48" fill="none" stroke="{BORDER}" stroke-width="7"/>
  <circle r="48" fill="none" stroke="{TITLE}" stroke-width="7" stroke-linecap="round"
          stroke-dasharray="301.6" stroke-dashoffset="301.6" transform="rotate(-90)">
    <animate attributeName="stroke-dashoffset" from="301.6" to="45" dur="1.2s" fill="freeze"/>
  </circle>
  <text y="4" text-anchor="middle" style="font:700 22px {FONT};fill:{TEXT}">{fmt(total)}</text>
  <text y="22" text-anchor="middle" class="m">contributions</text>
  <text y="72" text-anchor="middle" class="m">past 12 months</text>
</g>"""
    return card(450, 215, "GitHub Stats", "\n".join(body) + ring)


def render_languages(repos, top=8):
    totals, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n in IGNORE_LANGS:
                continue
            totals[n] = totals.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or MUTED
    items = sorted(totals.items(), key=lambda x: -x[1])[:top]
    s = sum(v for _, v in items) or 1
    bar, x, width = [], 25.0, 300
    for name, v in items:
        w = width * v / s
        bar.append(f'<rect x="{x:.2f}" y="52" width="{w:.2f}" height="10" fill="{colors[name]}"/>')
        x += w
    bar_svg = (
        f'<mask id="m"><rect x="25" y="52" width="{width}" height="10" rx="5" fill="#fff"/></mask>'
        f'<g mask="url(#m)">{"".join(bar)}</g>'
    )
    legend = []
    for i, (name, v) in enumerate(items):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 155, 92 + row * 28
        legend.append(
            f'<g class="fade" style="animation-delay:{i*100}ms" transform="translate({lx},{ly})">'
            f'<circle cx="5" cy="-4" r="5" fill="{colors[name]}"/>'
            f'<text x="16" y="0" class="l" style="font-size:12.5px">{esc(name)} '
            f'<tspan class="m">{100*v/s:.1f}%</tspan></text></g>'
        )
    return card(350, 215, "Most Used Languages", bar_svg + "\n".join(legend))


def render_activity(user, days=31):
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    pts = [d for w in weeks for d in w["contributionDays"]][-days:]
    W, H, L, R, T, B = 820, 260, 50, 25, 55, 45
    pw, ph = W - L - R, H - T - B
    mx = max([p["contributionCount"] for p in pts] + [4])
    step = pw / max(len(pts) - 1, 1)
    xy = [(L + i * step, T + ph - ph * p["contributionCount"] / mx) for i, p in enumerate(pts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"{L},{T+ph} {line} {L+pw},{T+ph}"
    grid = []
    for k in range(5):
        y = T + ph * k / 4
        val = round(mx * (4 - k) / 4)
        grid.append(f'<line x1="{L}" x2="{L+pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>')
        grid.append(f'<text x="{L-10}" y="{y+4:.1f}" text-anchor="end" class="m">{val}</text>')
    labels = []
    for i, p in enumerate(pts):
        if i % 5 == 0 or i == len(pts) - 1:
            d = datetime.date.fromisoformat(p["date"])
            labels.append(f'<text x="{xy[i][0]:.1f}" y="{H-20}" text-anchor="middle" class="m">{d.strftime("%b %d")}</text>')
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BG}" stroke="{ACCENT}" stroke-width="2"/>'
        for x, y in xy
    )
    body = f"""
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{TITLE}" stop-opacity=".45"/>
    <stop offset="1" stop-color="{TITLE}" stop-opacity="0"/>
  </linearGradient>
  <clipPath id="reveal"><rect x="0" y="0" width="0" height="{H}">
    <animate attributeName="width" from="0" to="{W}" dur="1.4s" fill="freeze"/>
  </rect></clipPath>
</defs>
{"".join(grid)}
<g clip-path="url(#reveal)">
  <polygon points="{area}" fill="url(#g)"/>
  <polyline points="{line}" fill="none" stroke="{TITLE}" stroke-width="2.5" stroke-linejoin="round"/>
  {dots}
</g>
{"".join(labels)}
<text x="{W-25}" y="36" text-anchor="end" class="m">contributions per day · last {days} days</text>
"""
    return card(W, H, "Contribution Activity", body)


# ---------------------------------------------------------------- markdown

def render_recent(repos, limit=5):
    lines = []
    for r in repos[:limit]:
        lang = f" `{r['primaryLanguage']['name']}`" if r["primaryLanguage"] else ""
        desc = f" · {r['description']}" if r["description"] else ""
        lines.append(f"- [**{r['name']}**]({r['url']}){lang}{desc} · _{day(r['pushedAt'])}_")
    return "\n".join(lines) or "_Nothing pushed recently._"


def render_releases(repos, limit=5):
    rel = [
        (x["publishedAt"], r["name"], x)
        for r in repos
        for x in r["releases"]["nodes"]
        if x["publishedAt"]
    ]
    rel.sort(reverse=True, key=lambda t: t[0])
    lines = [f"- [{n} {x['tagName']}]({x['url']}) · _{day(p)}_" for p, n, x in rel[:limit]]
    return "\n".join(lines) or "_No tagged releases yet._"


def render_npm():
    latest = fetch_json(f"https://registry.npmjs.org/{NPM_PACKAGE}/latest")
    monthly = fetch_json(f"https://api.npmjs.org/downloads/point/last-month/{NPM_PACKAGE}")
    return f"**v{latest['version']}** · **{monthly['downloads']:,}** downloads in the last month"


# ---------------------------------------------------------------- main

def main():
    readme = ROOT / "README.md"
    content = readme.read_text()
    token = os.environ.get("GH_TOKEN", "")

    try:
        user = fetch_user(token)
        repos = [
            r for r in user["repositories"]["nodes"]
            if r["name"] not in SKIP_REPOS and not r["isArchived"]
        ]
        write_if_changed(ASSETS / "stats.svg", render_stats(user, repos))
        write_if_changed(ASSETS / "languages.svg", render_languages(repos))
        write_if_changed(ASSETS / "activity.svg", render_activity(user))
        content = replace_chunk(content, "recent_repos", render_recent(repos))
        content = replace_chunk(content, "recent_releases", render_releases(repos))
    except Exception as exc:
        print(f"GitHub section skipped: {exc}")

    try:
        content = replace_chunk(content, "npm_stats", render_npm(), inline=True)
    except Exception as exc:
        print(f"npm section skipped: {exc}")

    readme.write_text(content)


if __name__ == "__main__":
    main()
