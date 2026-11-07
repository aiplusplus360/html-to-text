"""Extract the article from an HTML page and render clean Markdown.

Two problems, both usually solved by adding a dependency.

**Boilerplate removal.** A page's navigation, cookie banner, newsletter form and
"related articles" rail are the majority of its text and none of its content.
Rather than an ML model, this uses the signals a reader uses: text inside
``<p>`` elements, punctuation density, and **link density** — a container whose
text is mostly anchors is a menu, whatever its class name says.

**Faithful rendering.** ``HTMLParser`` gives you tags and text, not structure.
Rebuilding headings, nested lists, code blocks, links and tables as Markdown
requires a tree and an explicit block model, not a stream of ``handle_data``
callbacks.

>>> print(to_markdown("<h1>Title</h1><p>Hello <b>world</b>.</p>"))
# Title
<BLANKLINE>
Hello **world**.
>>> print(to_markdown("<ul><li>one</li><li>two</li></ul>"))
- one
- two
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

__all__ = [
    "Node",
    "parse",
    "to_markdown",
    "to_text",
    "extract_main",
    "main_content",
    "link_density",
]

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside",
         "nav", "ul", "ol", "li", "blockquote", "pre", "table", "tr", "td", "th",
         "h1", "h2", "h3", "h4", "h5", "h6", "figure", "figcaption", "hr", "form",
         "address", "dl", "dt", "dd", "thead", "tbody"}

DROP = {"script", "style", "noscript", "svg", "canvas", "iframe", "template",
        "head", "meta", "link"}

BOILERPLATE = re.compile(
    r"comment|sidebar|footer|nav|advert|\bads?\b|promo|cookie|share|social|"
    r"related|newsletter|subscribe|breadcrumb|menu|banner|modal|popup|paywall",
    re.IGNORECASE)

# Tags that cannot legally contain themselves; a new one implicitly closes the
# previous one, which is how HTML actually parses.
AUTO_CLOSE = {"p", "li", "dt", "dd", "tr", "td", "th", "option", "thead",
              "tbody", "tfoot"}


@dataclass
class Node:
    """A minimal DOM node: a tag, its attributes, and its children."""

    tag: str = "#document"
    attrs: Dict[str, str] = field(default_factory=dict)
    parent: Optional["Node"] = None
    children: List[Union["Node", str]] = field(default_factory=list)

    def append(self, child: Union["Node", str]) -> None:
        if isinstance(child, Node):
            child.parent = self
        self.children.append(child)

    def iter(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.iter()

    def find_all(self, tags: Sequence[str]) -> List["Node"]:
        wanted = set(tags)
        return [node for node in self.iter() if node.tag in wanted]

    @property
    def text(self) -> str:
        parts: List[str] = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in DROP:
                    continue
                parts.append(child.text)
            else:
                parts.append(child)
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    @property
    def raw_text(self) -> str:
        """Text with original whitespace, for ``<pre>`` and code."""
        parts: List[str] = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in DROP:
                    continue
                parts.append(child.raw_text)
            else:
                parts.append(child)
        return "".join(parts)

    @property
    def link_text(self) -> int:
        total = 0
        for node in self.iter():
            if node.tag == "a":
                total += len(node.text)
        return total


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack: List[Node] = [self.root]

    def _close_implicit(self, tag: str) -> None:
        # Only the innermost element can be implicitly closed. Searching the
        # whole stack would let a nested <li> close its parent <li> *and* the
        # <ul> that contains it.
        if tag in AUTO_CLOSE and len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_starttag(self, tag, attrs):
        self._close_implicit(tag)
        node = Node(tag=tag, attrs={key: value or "" for key, value in attrs})
        self.stack[-1].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag=tag, attrs={key: value or "" for key, value in attrs})
        self.stack[-1].append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].append(data)


def parse(html: str) -> Node:
    """Parse HTML into a node tree, tolerating unclosed tags.

    >>> parse("<p>a<p>b").find_all(["p"])[1].text
    'b'
    """
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def link_density(node: Node) -> float:
    """Fraction of visible text that sits inside anchors.

    >>> link_density(parse("<div><a href='/'>Menu</a> about</div>"))
    0.4
    """
    total = len(node.text)
    if not total:
        return 0.0
    return round(node.link_text / total, 6)


def _boilerplate(node: Node) -> bool:
    marker = " ".join([node.attrs.get("class", ""), node.attrs.get("id", ""),
                       node.attrs.get("role", "")])
    return bool(marker and BOILERPLATE.search(marker))


def _inside_boilerplate(node: Node) -> bool:
    current: Optional[Node] = node
    while current is not None:
        if _boilerplate(current):
            return True
        current = current.parent
    return False


def _score(node: Node) -> float:
    paragraphs = node.find_all(["p"])
    prose = sum(len(paragraph.text) for paragraph in paragraphs)
    punctuation = sum(paragraph.text.count(",") + paragraph.text.count(".")
                      for paragraph in paragraphs)
    score = prose + punctuation * 20.0
    density = link_density(node)
    if density > 0.5:
        score *= max(0.0, 1.0 - density)
    if node.tag in ("article", "main"):
        score *= 1.5
    if _boilerplate(node):
        score *= 0.25
    return score


def extract_main(html: str) -> Node:
    """Pick the container that holds the article, falling back to the body.

    >>> extract_main("<body><nav>menu</nav><article><p>" + "x " * 50 + "</p></article></body>").tag
    'article'
    """
    root = parse(html)
    candidates = [node for node in root.iter()
                  if node.tag in ("article", "main", "div", "section", "td", "body")]
    if not candidates:
        return root
    scored = [(score, index, node) for index, node in enumerate(candidates)
              for score in [_score(node)]]
    best_score, _, best = max(scored, key=lambda item: (item[0], -item[1]))
    body = next((node for node in root.iter() if node.tag == "body"), None)
    if body is not None and best_score <= _score(body) * 1.05:
        return body
    return best


def _inline(node: Node, depth: int = 0) -> str:
    pieces: List[str] = []
    for child in node.children:
        if isinstance(child, str):
            pieces.append(re.sub(r"\s+", " ", child))
            continue
        tag = child.tag
        if tag in DROP or tag in ("hr",):
            continue
        if tag in ("br",):
            pieces.append("  \n")
            continue
        if tag in ("strong", "b"):
            pieces.append("**%s**" % _inline(child, depth).strip())
        elif tag in ("em", "i"):
            pieces.append("*%s*" % _inline(child, depth).strip())
        elif tag in ("code", "tt"):
            pieces.append("`%s`" % child.text)
        elif tag == "a":
            href = child.attrs.get("href", "").strip()
            label = _inline(child, depth).strip() or child.text
            pieces.append("[%s](%s)" % (label, href) if href else label)
        elif tag == "img":
            alt = child.attrs.get("alt", "").strip()
            if alt:
                pieces.append("![%s](%s)" % (alt, child.attrs.get("src", "")))
        elif tag in ("ul", "ol", "table", "pre"):
            # Rendered as their own block by _render; do not inline the text.
            continue
        else:
            pieces.append(_inline(child, depth))
    return "".join(pieces)


def _clean(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _render(node: Node, depth: int = 0) -> List[str]:
    """Render a node into Markdown blocks."""
    if node.tag in DROP or _boilerplate(node):
        return []
    tag = node.tag
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        return ["%s %s" % ("#" * level, _clean(_inline(node)))]
    if tag == "p":
        text = _clean(_inline(node))
        return [text] if text else []
    if tag == "pre":
        content = node.raw_text.strip("\n").strip()
        return ["```\n%s\n```" % content] if content else []
    if tag in ("ul", "ol"):
        items = []
        for index, child in enumerate(node.children, start=1):
            if not isinstance(child, Node) or child.tag != "li":
                continue
            marker = "-" if tag == "ul" else "%d." % index
            body = _clean(_inline(child))
            nested = [block for sub in child.children
                      if isinstance(sub, Node) and sub.tag in ("ul", "ol")
                      for block in _render(sub, depth + 1)]
            items.append("%s %s" % (marker, body) if body else marker)
            for block in nested:
                items.extend("  " + line for line in block.splitlines())
        return ["\n".join(items)] if items else []
    if tag == "blockquote":
        inner = _render_children(node)
        return ["> " + line if line else ">" for line in inner.splitlines()]
    if tag == "table":
        rendered = _render_table(node)
        return [rendered] if rendered else []
    if tag == "hr":
        return ["---"]
    if tag in BLOCK:
        return _render_children(node)
    text = _clean(_inline(node))
    return [text] if text else []


def _render_children(node: Node) -> str:
    blocks: List[str] = []
    inline_buffer: List[str] = []

    def flush():
        if inline_buffer:
            text = _clean("".join(inline_buffer))
            if text:
                blocks.append(text)
            inline_buffer.clear()

    for child in node.children:
        if isinstance(child, str):
            inline_buffer.append(child)
            continue
        if child.tag in BLOCK or child.tag in DROP or child.tag in ("br",):
            flush()
            blocks.extend(_render(child))
        else:
            inline_buffer.append(_inline(Node(children=[child])))
    flush()
    return "\n\n".join(blocks)


def _render_table(node: Node) -> str:
    rows: List[List[str]] = []
    header = False
    for row in node.find_all(["tr"]):
        cells = [cell for cell in row.children
                 if isinstance(cell, Node) and cell.tag in ("td", "th")]
        if not cells:
            continue
        if not rows and all(cell.tag == "th" for cell in cells):
            header = True
        rows.append([_clean(_inline(cell)) or " " for cell in cells])
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [" "] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def to_markdown(html: str, main_only: bool = True) -> str:
    """Convert HTML to Markdown, optionally trimming to the main content.

    >>> to_markdown("<p>a</p><p>b</p>", main_only=False)
    'a\\n\\nb'
    """
    root = extract_main(html) if main_only else parse(html)
    return _render_children(root)


def to_text(html: str, main_only: bool = True) -> str:
    """Plain text with block boundaries preserved.

    >>> to_text("<h1>T</h1><p>x</p>", main_only=False)
    'T\\n\\nx'
    """
    root = extract_main(html) if main_only else parse(html)
    blocks = [node.text for node in root.iter()
              if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li",
                              "blockquote", "pre", "td", "th")
              and not _inside_boilerplate(node)]
    return "\n\n".join(block for block in blocks if block)


def main_content(html: str) -> str:
    """The text of the selected container, before Markdown rendering."""
    return extract_main(html).text
