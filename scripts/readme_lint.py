"""Lint a public README for the mechanical parts of the entry-page rules
(CONTRIBUTING.md "Writing docs" in public repositories, DOC-PHILOSOPHY.md "Entry pages" in private ones).

Usage: py -3 readme_lint.py <README.md> [--max-words 60]
       py -3 readme_lint.py --self-test
Exit 0 when no FAIL; WARN lines do not fail. Exit 0 is not compliance: a reviewer checks the rest.
"""
import html
import os
import re
import sys
import tempfile
import urllib.parse

VERSION = "7"
SLOP = [
    r"\betc\b\.?", r"\bnot (just|only)\b[^.]*\bbut\b", r"\bwhether you'?re\b",
    r"\b(seamless(ly)?|robust|powerful|leverag\w*|cutting[- ]edge|comprehensive|delve|unlock|empower\w*|"
    r"game[- ]chang\w*|supercharg\w*|effortless(ly)?|elevate|harness the|in today'?s|revolutioni\w*)\b",
    r"[A-Za-z)] ?[—–] ?[A-Za-z(]",  # a dash joining words; numeric ranges such as 1-3 pass
]
SECTIONS = {
    "why": r"why|problem|what it (does|solves)",
    "quick start": r"quick ?start|install|getting started|try it",
    "features": r"feature|what you get|highlights",
    "docs": r"doc|learn more|read next|reference",
}
BADGE = r"shields\.io|badge|/actions/workflows/|codecov|pepy\.tech"
BOX = r"[┌┐└┘│─]|\+-{3,}\+"


def _blank(m):
    return "\n" * m.group(0).count("\n")


def strip_code(text):
    """Remove backtick and tilde fences, <pre> and <code>, inline code and comments, keeping line count."""
    text = re.sub(
        r"^ {0,3}(`{3,})[^\n]*\n.*?^ {0,3}\1`*[ \t]*$|"
        r"^ {0,3}(~{3,})[^\n]*\n.*?^ {0,3}\2~*[ \t]*$",
        _blank, text, flags=re.S | re.M,
    )
    text = re.sub(r"^(?: {4}|\t)[^\n]*(?:\n|$)", _blank, text, flags=re.M)
    text = re.sub(r"<!--.*?-->|<pre\b.*?</pre>|<code\b.*?</code>", _blank, text, flags=re.S | re.I)
    return re.sub(r"(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)", _blank, text)


def refs(text):
    """Reference-style link definitions: label -> target."""
    return {k.lower(): v for k, v in re.findall(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s|$)", text, re.M)}


def slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def visible(text):
    """Reader-visible prose: no code, URLs, image sources, link definitions or markup."""
    t = strip_code(text)
    t = re.sub(r"</p>|<br\s*/?>", "\n\n", t, flags=re.I)
    t = re.sub(r"^\s{0,3}\[[^\]]+\]:.*$", "", t, flags=re.M)
    t = re.sub(r"!?\[([^\]]*)\]\[[^\]]*\]", r"\1", t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"https?://\S+", "", t)
    return html.unescape(t)


def images(text):
    """Distinct figure sources from Markdown, reference-style or HTML image syntax outside code."""
    t = strip_code(text)
    r = refs(t)
    srcs = re.findall(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)", t)
    srcs += [r.get((b or a).lower(), "") for a, b in re.findall(r"!\[([^\]]*)\]\[([^\]]*)\]", t)]
    srcs += re.findall(r"<(?:img|source|video)[^>]+?(?:src|srcset)=[\"']([^\"' ]+)", t, re.I)
    return list(dict.fromkeys(s for s in srcs if s and not re.search(BADGE, s, re.I)))


def headings(code_free):
    md = re.findall(r"^#{1,6} (.+)$", code_free, re.M)
    tags = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", code_free, re.I | re.S)
    md += re.findall(r"^ {0,3}(\S[^\n]*)\n {0,3}(?:=+|-+)[ \t]*$", code_free, re.M)
    return md + [re.sub(r"<[^>]+>", "", h) for h in tags]


def lint(text, path=".", max_words=60):
    fails, warns = [], []
    vis = visible(text)
    words_per = []
    for para in re.split(r"\n\s*\n", vis):
        lines = [l for l in para.splitlines() if l.strip() and not re.match(r"\s*(#|\|)", l)]
        if not lines or all(re.match(r"\s*([-*+] |\d+\. )", l) for l in lines):
            continue
        n = len(re.findall(r"\w+", " ".join(lines)))
        if n:
            words_per.append(n)
            if n > max_words:
                ln = vis[: vis.find(para)].count("\n") + 1
                fails.append(f"FAIL prose wall: paragraph at line {ln} has {n} words (max {max_words})")
    for pat in SLOP:
        for m in re.finditer(pat, vis, re.I):
            fails.append(f"FAIL style: line {vis.count(chr(10), 0, m.start()) + 1} matches {m.group(0)!r}")
    figs = images(text)
    if len(figs) < 2:
        fails.append(f"FAIL figures: {len(figs)} distinct figure(s) besides badges (need at least 2)")
    code_free = strip_code(text)
    first = re.search(r"^## |<h2\b|^ {0,3}\S[^\n]*\n {0,3}-+[ \t]*$", code_free, re.M | re.I)
    head = code_free[: first.start()] if first else code_free
    hero = images(head + "\n" + "\n".join(f"[{k}]: {v}" for k, v in refs(code_free).items()))
    hero = [h for h in hero if h in images(head) or re.search(r"!\[[^\]]*\]\[", head)]
    if not hero:
        fails.append("FAIL hero: no figure before the first ## section")
    elif not any(re.search(r"\.(gif|webp|mp4|webm)\b|user-attachments/assets", s, re.I) for s in hero):
        warns.append("WARN hero is static; use an animation where motion helps explain the task")
    if re.search(r"^(`{3,}|~{3,})\s*mermaid", text, re.M | re.I) or re.search(BOX, visible(text)):
        fails.append("FAIL diagram source on the entry page; use a rendered figure")
    hlist = headings(code_free)
    heads = " ".join(hlist).lower()
    for name, pat in SECTIONS.items():
        if not re.search(pat, heads):
            fails.append(f"FAIL section: no heading for '{name}'")
    base = os.path.dirname(os.path.abspath(path))
    anchors = set()
    for heading in hlist:
        root = slug(heading)
        anchor, suffix = root, 0
        while anchor in anchors:  # GitHub numbers duplicate headings: docs, docs-1
            suffix += 1
            anchor = f"{root}-{suffix}"
        anchors.add(anchor)
    anchors.update(re.findall(r"<a[^>]+(?:name|id)=[\"']([^\"']+)", code_free, re.I))
    targets = re.findall(r"\]\(\s*<?([^)\s>]+)", code_free) + list(refs(code_free).values())
    targets += re.findall(r"<(?:a|img)[^>]+(?:href|src)=[\"']([^\"']+)", code_free, re.I)
    for target in set(targets):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        local, _, frag = urllib.parse.unquote(target).partition("#")
        if local and path != "." and not os.path.exists(os.path.join(base, local)):
            fails.append(f"FAIL link: local target {local} does not exist")
        elif not local and frag and frag.lower() not in anchors:
            fails.append(f"FAIL link: anchor #{frag} matches no heading")
    size = len(text.encode("utf-8"))
    if size > 16384:
        warns.append(f"WARN size {size} bytes over 16 KB; move detail to linked pages")
    mean = sum(words_per) / len(words_per) if words_per else 0
    if mean > 30:
        warns.append(f"WARN mean paragraph {mean:.0f} words; aim for most under 25")
    return fails, warns, f"{len(words_per)} paragraphs, mean {mean:.0f} words; {len(figs)} figures; {size} bytes"


def self_test():
    style = lambda s: [f for f in lint(s)[0] if f.startswith("FAIL style")]
    assert not style("Readers etch files.")
    assert not style("Run `cat /etc/config` first.")
    assert not style("Pick 1–3 items.")
    assert style("It reads files, etc.")
    assert style("It reads files — then it stops.")
    assert not style("~~~text\ncat /etc/config\n~~~\n")
    assert not style("<pre><code>cat /etc/config</code></pre>\n")
    assert not style("Run this:\n\n    cat /etc/config\n")
    assert not style("Run ``cat /etc/config`` first, or ``echo `x` etc`` too.")
    under = "Why\n===\n\nQuick start\n-----------\n\nFeatures\n--------\n\nDocs\n----\n"
    assert not any("FAIL section" in f for f in lint(under)[0])
    assert not any("anchor" in f for f in lint("## Docs\n\n## Docs\n\n[Second docs](#docs-1)\n")[0])
    assert not style("```\ncat /etc/config\n````\n")
    assert images("![x](https://img.shields.io/b.svg)") == []
    assert images("https://example.org/hero.gif") == []
    assert images("```\n![x](a.png)\n```") == []
    assert images("~~~\n![a](a.png)\n~~~") == []
    assert images("![Working output](hero.jpg)") == ["hero.jpg"]
    assert images("![a](h.png) and ![b](h.png)") == ["h.png"]
    assert images("![Run][r]\n\n[r]: run.gif\n") == ["run.gif"]
    doc = lambda s: lint(s)[0]
    assert any("prose wall" in f for f in doc("<p>" + "word " * 70 + "</p>\n"))
    assert not any("prose wall" in f for f in doc("<p>" + "word " * 31 + "</p>\n<p>" + "word " * 31 + "</p>\n"))
    assert not any("'why'" in f for f in doc("<h2>Why this project</h2>\n"))
    assert any("anchor #nope" in f for f in doc("[x](#nope)\n## Real\n"))
    assert not any("anchor" in f for f in doc("[x](#real)\n## Real\n"))
    assert any("hero" in f for f in doc("Intro\n\nWhy\n---\n\n![a](a.png) ![b](b.png)\n"))
    assert not any("hero" in f for f in doc("![a](a.png)\n\nWhy\n---\n\n![b](b.png)\n"))
    assert any("diagram source" in f for f in doc("a\n\n+----+\n| x |\n+----+\n"))
    assert any("diagram source" in f for f in doc("~~~mermaid\ngraph TD\n~~~\n"))
    assert not any("hero" in f for f in doc("![Run][r]\n\n## Next\n\n[r]: run.gif\n"))
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a1.md"), "w").close()
    rd = os.path.join(d, "README.md")
    assert not any("link" in f for f in lint("[Review](a1%2Emd)\n", rd)[0])
    missing = lint('<a href="missing.md">x</a>\n[y][m]\n\n[m]: missing.md\n', rd)[0]
    assert any("missing.md" in f for f in missing)
    print("self-test passed")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--self-test"]:
        self_test()
        sys.exit(0)
    mw = 60
    if "--max-words" in args:
        i = args.index("--max-words")
        mw = int(args[i + 1])
        del args[i:i + 2]
    fails, warns, summary = lint(open(args[0], encoding="utf-8").read(), args[0], mw)
    for line in fails + warns:
        print(line)
    print(f"readme_lint v{VERSION}: {len(fails)} fail, {len(warns)} warn; {summary}")
    sys.exit(1 if fails else 0)
