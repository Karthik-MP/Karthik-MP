"""Rebuild the dynamic sections of README.md.

Run by .github/workflows/build.yml on a schedule. Each section lives between
<!-- name starts --> and <!-- name ends --> markers. If a data source fails,
that section is left as it was, so a bad network day never blanks the README.
"""

import datetime
import json
import os
import pathlib
import re
import urllib.request

USER = "Karthik-MP"
NPM_PACKAGE = "langgraph-ui-components"
SKIP_REPOS = {USER}  # don't list the profile repo itself
ROOT = pathlib.Path(__file__).parent.resolve()

GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                 isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        url
        description
        pushedAt
        isArchived
        primaryLanguage { name }
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { name tagName publishedAt url }
        }
      }
    }
  }
}
"""


def fetch_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", f"{USER}-readme-builder")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def replace_chunk(content, marker, chunk, inline=False):
    pattern = re.compile(
        rf"<!-- {marker} starts -->.*<!-- {marker} ends -->", re.DOTALL
    )
    if not inline:
        chunk = f"\n{chunk}\n"
    return pattern.sub(
        lambda _: f"<!-- {marker} starts -->{chunk}<!-- {marker} ends -->", content
    )


def fetch_repos(token):
    body = json.dumps({"query": GRAPHQL_QUERY, "variables": {"login": USER}})
    data = fetch_json(
        "https://api.github.com/graphql",
        data=body.encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return [
        r
        for r in data["data"]["user"]["repositories"]["nodes"]
        if r["name"] not in SKIP_REPOS and not r["isArchived"]
    ]


def day(iso):
    return iso.split("T")[0]


def render_recent(repos, limit=5):
    lines = []
    for r in repos[:limit]:
        lang = f" `{r['primaryLanguage']['name']}`" if r["primaryLanguage"] else ""
        desc = f" · {r['description']}" if r["description"] else ""
        lines.append(f"- [**{r['name']}**]({r['url']}){lang}{desc} · _{day(r['pushedAt'])}_")
    return "\n".join(lines) or "_Nothing pushed recently._"


def render_releases(repos, limit=5):
    releases = []
    for r in repos:
        for rel in r["releases"]["nodes"]:
            if rel["publishedAt"]:
                releases.append((rel["publishedAt"], r["name"], rel))
    releases.sort(reverse=True, key=lambda x: x[0])
    lines = [
        f"- [{name} {rel['tagName']}]({rel['url']}) · _{day(published)}_"
        for published, name, rel in releases[:limit]
    ]
    return "\n".join(lines) or "_No tagged releases yet._"


def render_npm():
    latest = fetch_json(f"https://registry.npmjs.org/{NPM_PACKAGE}/latest")
    weekly = fetch_json(
        f"https://api.npmjs.org/downloads/point/last-week/{NPM_PACKAGE}"
    )
    return (
        f"**v{latest['version']}** · **{weekly['downloads']:,}** downloads last week"
    )


def main():
    readme = ROOT / "README.md"
    content = readme.read_text()
    token = os.environ.get("GH_TOKEN", "")

    try:
        repos = fetch_repos(token)
        content = replace_chunk(content, "recent_repos", render_recent(repos))
        content = replace_chunk(content, "recent_releases", render_releases(repos))
    except Exception as exc:  # keep old content on failure
        print(f"GitHub section skipped: {exc}")

    try:
        content = replace_chunk(content, "npm_stats", render_npm(), inline=True)
    except Exception as exc:
        print(f"npm section skipped: {exc}")

    readme.write_text(content)


if __name__ == "__main__":
    main()
