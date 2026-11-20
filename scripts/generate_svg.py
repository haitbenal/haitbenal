#!/usr/bin/env python3
"""Generate the profile card SVG (dark.svg) with live GitHub stats.

Reads the braille ASCII art from ascii-art.txt, fetches stats from the
GitHub GraphQL API and writes dark.svg. Uses only the standard library.

Env:
  GH_TOKEN / GITHUB_TOKEN  token for the GitHub API (required for stats)
  GH_USER                  GitHub login (default: haitbenal)
"""

import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ART_FILE = ROOT / "ascii-art.txt"
OUT_FILE = ROOT / "dark.svg"
USER = os.environ.get("GH_USER", "haitbenal")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

# ---- Static profile info (edit freely) ----------------------------------
NAME = "Hichame Ait Benalla"
PROFILE = [
    ("Role", "Full-Stack Developer Student"),
    ("Uptime", "{uptime}"),  # GitHub account age, filled in live
    ("Location", "Morocco"),
    ("School", "Zone 01 Oujda"),
    ("Hobbies", "Pool, Coding"),
]
SECTIONS = [
    ("Languages", [
        ("Programming", "Go, Python, JavaScript, PHP"),
        ("Learning", "Java, Rust"),
    ]),
    ("Development", [
        ("Frontend", "HTML, CSS, Tailwind CSS"),
        ("Database", "MySQL"),
        ("Tools", "Git, GitHub, GitLab, Bash"),
    ]),
    ("GitHub Stats", [
        ("Repos", "{repos} {{Contributed: {contributed}}}"),
        ("Stars", "{stars} | Forks: {forks}"),
        ("Commits", "{commits}"),
        ("Contribs", "{contribs_year} in the last year"),
        ("PRs", "{prs} | Issues: {issues}"),
        ("Followers", "{followers} | Following: {following}"),
    ]),
    ("Contact", [
        ("Email", "its.aitbenalla.hichame@gmail.com"),
        ("LinkedIn", "hichame-ait-benalla"),
        ("GitHub", USER),
    ]),
]

# ---- Look ----------------------------------------------------------------
BG, BORDER = "#000000", "#30363d"
FG, DIM, KEY, ART = "#e6edf3", "#6e7681", "#C2477A", "#e6edf3"
FONT_SIZE = 14
CHAR_W = 8.4          # monospace advance at 14px
ROW_H = 18
ART_X, ART_Y = 30, 40
ART_LINE_H = 14       # braille line height
ART_CHAR_W = 7        # braille cells are 1:2, so width = line height / 2
KEY_COLS = 17         # ". Key: ....." always spans this many columns
HEADER_COLS = 50      # "- Section -----" total width


# ---- GitHub API ----------------------------------------------------------
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-svg"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats():
    base = gql(
        """query($login: String!) {
          user(login: $login) {
            createdAt
            followers { totalCount }
            following { totalCount }
            pullRequests { totalCount }
            issues { totalCount }
            repositoriesContributedTo(
              contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
            ) { totalCount }
            contributionsCollection {
              contributionCalendar { totalContributions }
            }
          }
        }""",
        {"login": USER},
    )["user"]

    # Owned repos: count, stars, forks (paginated)
    repos = stars = forks = 0
    cursor = None
    while True:
        page = gql(
            """query($login: String!, $after: String) {
              user(login: $login) {
                repositories(ownerAffiliations: OWNER, first: 100, after: $after) {
                  totalCount
                  nodes { stargazerCount forkCount }
                  pageInfo { hasNextPage endCursor }
                }
              }
            }""",
            {"login": USER, "after": cursor},
        )["user"]["repositories"]
        repos = page["totalCount"]
        for n in page["nodes"]:
            stars += n["stargazerCount"]
            forks += n["forkCount"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # All-time commits: contributionsCollection is limited to 1 year per query
    created = dt.datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    commits = 0
    start = created
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        cc = gql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  totalCommitContributions
                  restrictedContributionsCount
                }
              }
            }""",
            {"login": USER, "from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]
        # Commits the token can see + private contributions GitHub hides from
        # it (mostly commits in private/org repos; ~0 with a full-scope token).
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        start = end

    return {
        "uptime": age(created, now),
        "repos": repos,
        "contributed": base["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "forks": forks,
        "commits": f"{commits:,}",
        "contribs_year": f"{base['contributionsCollection']['contributionCalendar']['totalContributions']:,}",
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "followers": base["followers"]["totalCount"],
        "following": base["following"]["totalCount"],
    }


def age(start, now):
    years = now.year - start.year
    months = now.month - start.month
    days = now.day - start.day
    if days < 0:
        months -= 1
        prev_month_end = now.replace(day=1) - dt.timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        years -= 1
        months += 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


# ---- SVG -----------------------------------------------------------------
def text(x, y, inner, **attrs):
    a = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<text x="{x:.1f}" y="{y:.1f}"{a} xml:space="preserve">{inner}</text>'


def build_svg(stats):
    art = ART_FILE.read_text(encoding="utf-8").splitlines()
    art_cols = max(len(line) for line in art)
    art_w = art_cols * ART_CHAR_W
    info_x = ART_X + art_w + 30
    val_x = info_x + KEY_COLS * CHAR_W

    out = []
    # ASCII art: textLength pins every line to the same width regardless of
    # how the viewer's font sizes braille glyphs.
    for i, line in enumerate(art):
        y = ART_Y + (i + 1) * ART_LINE_H
        out.append(text(ART_X, y, escape(line.ljust(art_cols, "⠀")),
                        fill=ART, font_size=ART_LINE_H,
                        textLength=f"{art_w:.0f}", lengthAdjust="spacingAndGlyphs"))

    y = 50.0
    out.append(text(info_x, y, f'{escape(NAME)} <tspan fill="{DIM}" font-weight="normal">'
                    f'{"-" * (HEADER_COLS - len(NAME) - 1)}</tspan>',
                    fill=FG, font_weight="bold"))
    y += ROW_H

    def row(key, value):
        dots = "." * (KEY_COLS - len(key) - 4)
        out.append(text(info_x, y, f'<tspan fill="{DIM}">. </tspan>'
                        f'<tspan fill="{KEY}" font-weight="bold">{escape(key)}</tspan>'
                        f'<tspan fill="{DIM}">: {dots}</tspan>'))
        out.append(text(val_x, y, escape(value.format(**stats)), fill=FG))

    for k, v in PROFILE:
        y += ROW_H
        row(k, v)
    for title, rows in SECTIONS:
        y += ROW_H * 2
        dashes = "-" * (HEADER_COLS - len(title) - 3)
        out.append(text(info_x, y, f'- <tspan fill="{FG}">{escape(title)}</tspan> {dashes}', fill=DIM))
        for k, v in rows:
            y += ROW_H
            row(k, v)

    art_bottom = ART_Y + len(art) * ART_LINE_H
    height = int(max(art_bottom, y) + 40)
    width = int(val_x + 36 * CHAR_W)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("updated %Y-%m-%d")
    out.append(text(width - 20, height - 14, stamp, fill=DIM, font_size=11, text_anchor="end"))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace,SFMono-Regular,Menlo,'
        f"Consolas,'Liberation Mono',monospace\" font-size=\"{FONT_SIZE}\">\n"
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12" '
        f'fill="{BG}" stroke="{BORDER}"/>\n' + "\n".join(out) + "\n</svg>\n"
    )


def main():
    if TOKEN:
        stats = fetch_stats()
    else:
        print("No GH_TOKEN/GITHUB_TOKEN set: using placeholder stats.")
        stats = {k: "?" for k in ("uptime", "repos", "contributed", "stars", "forks",
                                  "commits", "contribs_year", "prs", "issues",
                                  "followers", "following")}
    OUT_FILE.write_text(build_svg(stats), encoding="utf-8")
    print(f"Wrote {OUT_FILE.relative_to(ROOT)}: {stats}")


if __name__ == "__main__":
    main()
