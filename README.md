# html-to-text

Turn a page into the article, not the navigation.

Most "HTML to text" utilities concatenate every text node in the document. That is
why scrapers so often return a cookie banner, nine menu items, and then, finally,
the sentence you wanted. `html-to-text` isolates the content container first and
renders Markdown from it — with **zero dependencies**, using only `html.parser`.

```console
$ pip install -e .
$ html-to-text markdown page.html
# Why extraction is hard

Boilerplate dominates most pages, so naive text scrapers return menus.

- First point
- Second point
```

## Why this exists

RAG pipelines and content aggregators fail in a specific, boring way: the chunk
that gets embedded is navigation chrome. The model then answers confidently about
"Products" and "Accept all cookies". Fixing this usually means pulling in a large
scraping dependency, which is a hard sell inside a restricted environment.

`html-to-text` is the small, auditable version of that fix:

- **Content isolation** — the best block by text mass penalised by link density.
- **Boilerplate detection** — `class`, `id`, and `role` markers such as `sidebar`,
  `cookie`, `site-nav`, `footer`, `promo`.
- **Clean Markdown** — headings, nested lists, block quotes, fenced code, and
  GitHub-style tables.
- **Plain text mode** for summarisation and token counting.
- **Audit mode** so you can see *why* a container was selected.

## Install

```console
git clone https://github.com/aiplusplus360/html-to-text
cd html-to-text
python -m pip install -e .
```

Python 3.9+. No runtime dependencies.

## CLI

```console
html-to-text markdown page.html                 # article Markdown
html-to-text markdown page.html --whole-document
html-to-text text page.html                     # plain text
curl -s https://example.com | html-to-text markdown -
html-to-text audit page.html --json
```

`audit` reports the winner:

```json
[
  {
    "source": "page.html",
    "tag": "article",
    "class": "post",
    "id": "",
    "link_density": 0.0,
    "characters": 412
  }
]
```

Exit codes are `0` on success and non-zero when a file cannot be read, so the
command is safe to use in a pipeline with `set -e`.

## Library

```python
from htmltotext import to_markdown, to_text, extract_main, link_density

markdown = to_markdown(html)                 # main content only
everything = to_markdown(html, main_only=False)
plain = to_text(html)

root = extract_main(html)
print(root.tag, link_density(root))
```

## How the extraction works

1. Parse with `html.parser` into a forgiving tree. Void elements are handled,
   implicit `</p>` / `</li>` / `</td>` closes are applied, and `script`,
   `style`, `svg`, `iframe`, and `head` are dropped entirely.
2. Score every block element as

   \[
   \text{score} = \text{text mass} \times (1 - \min(1, \text{link density})) \times \text{boilerplate penalty}
   \]

3. Descend from the best-scoring `<body>` child towards the densest descendant,
   stopping when a child no longer improves on its parent.
4. Render the chosen subtree. Elements inside a boilerplate container are skipped
   even when a parent was included, which is what removes inline nav bars.

Link density is the ratio of characters inside `<a>` elements to total characters,
so a footer made entirely of links scores near `1.0` and disappears.

## Markdown coverage

| Input | Output |
| --- | --- |
| `<h1>`–`<h6>` | ATX headings |
| `<p>`, `<div>`, `<section>` | blank-line separated blocks |
| `<ul>`, `<ol>`, nested lists | `- ` / `1. ` with two-space indentation per level |
| `<blockquote>` | `> ` prefixed lines |
| `<pre>`, `<code>` | fenced triple-backtick blocks |
| `<table>` with `<th>` | GitHub pipe table with separator row |
| `<table>` without `<th>` | tab-separated cells |
| `<hr>` | `---` |
| `<br>` | soft line break |

Malformed tables (ragged rows) are padded rather than crashing, because real
pages are malformed.

## Testing

```console
python -m unittest discover -s tests -v   # 46 tests
python -m doctest htmltotext/core.py
```

The suite covers parser recovery, nested list indentation, table padding,
boilerplate suppression, link density, CLI contract, and file/stdin handling.

## Design notes

- **No regex-based HTML splitting.** Entity handling, attribute quoting, and
  self-closing tags all break naive splitting; `html.parser` already solves it.
- **No heuristics that need a network call or a model.** Extraction has to be
  fast, deterministic, and offline.
- **Indentation is explicit, not inferred.** Nested lists indent by depth, so the
  output round-trips through any Markdown renderer.

## License

MIT.
