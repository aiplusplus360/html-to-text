"""``html-to-text`` command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .core import extract_main, link_density, main_content, to_markdown, to_text

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="html-to-text",
        description="Extract the article from a page and render clean Markdown.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("markdown", help="render Markdown (default)")
    dump.add_argument("files", nargs="*", help="HTML files; '-' reads stdin")
    dump.add_argument("--whole-document", action="store_true",
                      help="keep navigation and boilerplate instead of isolating the article")
    dump.add_argument("-o", "--output", help="output file (default: stdout)")

    text = sub.add_parser("text", help="render plain text")
    text.add_argument("files", nargs="*", help="HTML files; '-' reads stdin")
    text.add_argument("--whole-document", action="store_true")
    text.add_argument("-o", "--output", help="output file (default: stdout)")

    audit = sub.add_parser("audit", help="report the content container that was chosen")
    audit.add_argument("files", nargs="*", help="HTML files; '-' reads stdin")
    audit.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def _read(files: List[str]) -> List[tuple]:
    if not files:
        return [("<stdin>", sys.stdin.read())]
    documents = []
    for name in files:
        if name == "-":
            documents.append(("<stdin>", sys.stdin.read()))
            continue
        try:
            documents.append((name, Path(name).read_text(encoding="utf-8", errors="replace")))
        except OSError as exc:
            raise SystemExit("cannot read %s: %s" % (name, exc))
    return documents


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    documents = _read(args.files)

    if args.command == "audit":
        rows = []
        for name, html in documents:
            root = extract_main(html)
            rows.append({
                "source": name,
                "tag": root.tag,
                "class": root.attrs.get("class", ""),
                "id": root.attrs.get("id", ""),
                "link_density": round(link_density(root), 4),
                "characters": len(main_content(html)),
            })
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print("%s -> <%s class=%r id=%r>" % (
                    row["source"], row["tag"], row["class"], row["id"]))
                print("  link density %.3f, %d characters" % (
                    row["link_density"], row["characters"]))
        return 0

    main_only = not args.whole_document
    render = to_markdown if args.command == "markdown" else to_text
    parts = [render(html, main_only) for _, html in documents]
    output = "\n\n".join(part for part in parts if part)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print("wrote %s" % args.output, file=sys.stderr)
    else:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")
    return 0
