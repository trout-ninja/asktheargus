#!/usr/bin/env python3
"""
journal.py — Minimal static journal publisher

Commands:
  python3 tools/journal.py new "First Entry"
  python3 tools/journal.py publish entries/2025-12-27.html

What it does:
- new: creates a new entry HTML file in /entries with a consistent template
- publish: updates index.html by:
    * replacing content between <!-- LATEST_START --> and <!-- LATEST_END -->
    * updating <!-- LATEST_META ... -->
    * rebuilding archive links between <!-- ARCHIVE START --> and <!-- ARCHIVE END -->
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]  # project/
INDEX = ROOT / "index.html"
ENTRIES_DIR = ROOT / "entries"


LATEST_META_RE = re.compile(r'<!--\s*LATEST_META\s+file="([^"]+)"\s+title="([^"]+)"\s*-->')
TITLE_H3_RE = re.compile(r"<h3>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
META_P_RE = re.compile(r'<p\s+class="entry-meta"\s*>(.*?)</p>', re.IGNORECASE | re.DOTALL)


@dataclass
class EntryInfo:
    rel_path: str          # entries/2025-12-27.html
    date_str: str          # 2025-12-27
    title_line: str        # 2025-12-27 — First Entry
    meta: str              # Setting up shop...
    sort_key: Tuple[int,int,int]  # (YYYY,MM,DD)


def slugify_title(title: str) -> str:
    # conservative: keep letters/numbers/spaces -> hyphens
    t = title.strip().lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t or "entry"


def ensure_markers_exist(html: str) -> None:
    required = [
        ("<!-- ARCHIVE START -->", "<!-- ARCHIVE END -->"),
        ("<!-- LATEST_START -->", "<!-- LATEST_END -->"),
    ]
    for a, b in required:
        if a not in html or b not in html:
            raise RuntimeError(f"index.html is missing required marker pair: {a} ... {b}")
    if "LATEST_META" not in html:
        raise RuntimeError('index.html is missing a LATEST_META comment.')


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def extract_entry_info(entry_path: Path) -> EntryInfo:
    content = read_text(entry_path)

    # Expect first <h3> inside entry to be "YYYY-MM-DD — Title"
    m_title = TITLE_H3_RE.search(content)
    if not m_title:
        raise RuntimeError("Entry file must contain an <h3>...</h3> title line.")
    title_line = re.sub(r"\s+", " ", m_title.group(1)).strip()

    # Attempt to parse leading date
    m_date = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+[—-]\s+(.+)", title_line)
    if not m_date:
        raise RuntimeError('Entry <h3> must start like: "YYYY-MM-DD — Title"')
    yyyy, mm, dd = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
    date_str = f"{yyyy:04d}-{mm:02d}-{dd:02d}"

    m_meta = META_P_RE.search(content)
    meta = ""
    if m_meta:
        meta = re.sub(r"\s+", " ", m_meta.group(1)).strip()

    rel_path = str(entry_path.relative_to(ROOT)).replace("\\", "/")
    return EntryInfo(
        rel_path=rel_path,
        date_str=date_str,
        title_line=title_line,
        meta=meta,
        sort_key=(yyyy, mm, dd),
    )


def list_entries() -> List[EntryInfo]:
    if not ENTRIES_DIR.exists():
        return []
    infos: List[EntryInfo] = []
    for p in sorted(ENTRIES_DIR.glob("*.html")):
        try:
            infos.append(extract_entry_info(p))
        except Exception:
            # Skip malformed entries rather than breaking publishing
            continue
    infos.sort(key=lambda e: e.sort_key, reverse=True)
    return infos


def replace_between_markers(html: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL
    )
    block = start + "\n" + replacement.rstrip() + "\n  " + end
    new_html, n = pattern.subn(block, html, count=1)
    if n != 1:
        raise RuntimeError(f"Could not replace block between {start} and {end} (found {n} matches).")
    return new_html


def update_latest_meta(html: str, latest: EntryInfo) -> str:
    # Replace the whole LATEST_META line if present; otherwise error
    def repl(match: re.Match) -> str:
        return f'<!-- LATEST_META file="{latest.rel_path}" title="{latest.title_line}" -->'

    new_html, n = LATEST_META_RE.subn(repl, html, count=1)
    if n != 1:
        raise RuntimeError('Could not find/replace LATEST_META line. Ensure it matches the format: <!-- LATEST_META file="..." title="..." -->')
    return new_html


def build_archive_ul(entries: List[EntryInfo]) -> str:
    # Only <li> lines (no <ul> wrapper) for insertion between markers
    lines = []
    for e in entries:
        lines.append(f'                <li><a href="{e.rel_path}">{e.date_str} - {e.title_line.split("—", 1)[-1].strip()}</a></li>')
    return "\n".join(lines) if lines else "                <!-- (no entries yet) -->"


def extract_latest_article_from_entry(entry_path: Path) -> str:
    # We assume the entry file contains an <article ...> ... </article> block.
    content = read_text(entry_path)
    m = re.search(r"(<article\b.*?</article>)", content, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        raise RuntimeError("Entry file must include a full <article>...</article> block.")
    return m.group(1).strip()


def cmd_new(title: str) -> Path:
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    slug = slugify_title(title)
    filename = f"{today}-{slug}.html"
    path = ENTRIES_DIR / filename

    # Template: you write inside the <section> blocks.
    template = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{today} — {title}</title>
  </head>
  <body>
    <article class="entry-card">
      <header class="entry-header">
        <h3>{today} — {title}</h3>
        <p class="entry-meta">One-line summary goes here.</p>
      </header>

      <section>
        <h4>Skills Learned (Summary)</h4>
        <ul>
          <li>Replace this</li>
          <li>Replace this</li>
        </ul>
      </section>

      <section>
        <h4>Captain's Log</h4>
        <p>Write your entry here.</p>
      </section>
    </article>
  </body>
</html>
"""
    if path.exists():
        raise RuntimeError(f"Entry already exists: {path}")
    write_text(path, template)
    return path


def cmd_publish(entry_rel: str) -> None:
    if not INDEX.exists():
        raise RuntimeError(f"Missing {INDEX}")
    entry_path = (ROOT / entry_rel).resolve()
    if not entry_path.exists():
        raise RuntimeError(f"Entry not found: {entry_path}")

    index_html = read_text(INDEX)
    ensure_markers_exist(index_html)

    # Build latest
    latest_article = extract_latest_article_from_entry(entry_path)
    latest_info = extract_entry_info(entry_path)

    # Rebuild archive from all entries (including the one you are publishing)
    entries = list_entries()

    # Update index.html
    index_html = update_latest_meta(index_html, latest_info)
    index_html = replace_between_markers(
        index_html,
        "<!-- LATEST_START -->",
        "<!-- LATEST_END -->",
        "  " + latest_article.replace("\n", "\n  ")
    )
    archive_block = build_archive_ul(entries)
    index_html = replace_between_markers(
        index_html,
        "<!-- ARCHIVE START -->",
        "<!-- ARCHIVE END -->",
        archive_block
    )

    write_text(INDEX, index_html)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Usage:\n  python3 tools/journal.py new \"Title\"\n  python3 tools/journal.py publish entries/yourfile.html")
        return 2

    cmd = argv[1].lower()

    try:
        if cmd == "new":
            if len(argv) < 3:
                raise RuntimeError('Provide a title: python3 tools/journal.py new "My Title"')
            title = " ".join(argv[2:]).strip()
            p = cmd_new(title)
            rel = p.relative_to(ROOT)
            print(f"Created: {rel}")
            print("Now edit that file, then run:")
            print(f"  python3 tools/journal.py publish {rel.as_posix()}")
            return 0

        if cmd == "publish":
            if len(argv) != 3:
                raise RuntimeError("Provide the entry path: python3 tools/journal.py publish entries/2025-12-27-first-entry.html")
            cmd_publish(argv[2])
            print("Published. index.html updated.")
            return 0

        raise RuntimeError(f"Unknown command: {cmd}")

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

