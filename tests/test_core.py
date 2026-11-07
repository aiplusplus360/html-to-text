import unittest

from htmltotext.core import (
    Node,
    extract_main,
    link_density,
    main_content,
    parse,
    to_markdown,
    to_text,
)


class ParseTests(unittest.TestCase):
    def test_simple_tree(self):
        root = parse("<p>hello</p>")
        paragraphs = root.find_all(["p"])
        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(paragraphs[0].text, "hello")

    def test_unclosed_paragraphs_are_siblings(self):
        paragraphs = parse("<p>a<p>b").find_all(["p"])
        self.assertEqual([node.text for node in paragraphs], ["a", "b"])

    def test_unclosed_list_items(self):
        items = parse("<ul><li>a<li>b</ul>").find_all(["li"])
        self.assertEqual([item.text for item in items], ["a", "b"])

    def test_void_elements_do_not_nest(self):
        root = parse("<p>a<br>b</p>")
        paragraph = root.find_all(["p"])[0]
        self.assertEqual(paragraph.text, "ab")

    def test_entities_decoded(self):
        self.assertEqual(parse("<p>a &amp; b</p>").find_all(["p"])[0].text, "a & b")

    def test_attributes(self):
        node = parse('<a href="/x" class="c">t</a>').find_all(["a"])[0]
        self.assertEqual(node.attrs["href"], "/x")
        self.assertEqual(node.attrs["class"], "c")

    def test_text_ignores_script(self):
        self.assertEqual(parse("<p>a<script>x=1</script></p>").find_all(["p"])[0].text, "a")

    def test_stray_end_tag_is_ignored(self):
        self.assertEqual(parse("<p>a</div>b</p>").find_all(["p"])[0].text, "ab")

    def test_raw_text_preserves_whitespace(self):
        pre = parse("<pre>a\n  b</pre>").find_all(["pre"])[0]
        self.assertEqual(pre.raw_text, "a\n  b")


class MarkdownTests(unittest.TestCase):
    def test_headings(self):
        self.assertEqual(to_markdown("<h2>Title</h2>", main_only=False), "## Title")

    def test_paragraphs_separated(self):
        self.assertEqual(to_markdown("<p>a</p><p>b</p>", main_only=False), "a\n\nb")

    def test_bold_and_italic(self):
        self.assertEqual(to_markdown("<p><b>b</b> and <i>i</i></p>", main_only=False),
                         "**b** and *i*")

    def test_link(self):
        self.assertEqual(to_markdown('<p><a href="/x">label</a></p>', main_only=False),
                         "[label](/x)")

    def test_link_without_href_is_text(self):
        self.assertEqual(to_markdown("<p><a>label</a></p>", main_only=False), "label")

    def test_inline_code(self):
        self.assertEqual(to_markdown("<p>use <code>x</code></p>", main_only=False),
                         "use `x`")

    def test_unordered_list(self):
        self.assertEqual(to_markdown("<ul><li>a</li><li>b</li></ul>", main_only=False),
                         "- a\n- b")

    def test_ordered_list(self):
        self.assertEqual(to_markdown("<ol><li>a</li><li>b</li></ol>", main_only=False),
                         "1. a\n2. b")

    def test_nested_list(self):
        rendered = to_markdown("<ul><li>a<ul><li>b</li></ul></li></ul>", main_only=False)
        self.assertIn("- a", rendered)
        self.assertIn("  - b", rendered)

    def test_pre_is_fenced(self):
        self.assertEqual(to_markdown("<pre><code>x = 1</code></pre>", main_only=False),
                         "```\nx = 1\n```")

    def test_pre_keeps_indentation(self):
        rendered = to_markdown("<pre>a\n  b</pre>", main_only=False)
        self.assertIn("  b", rendered)

    def test_blockquote(self):
        self.assertEqual(to_markdown("<blockquote><p>quoted</p></blockquote>",
                                     main_only=False), "> quoted")

    def test_horizontal_rule(self):
        self.assertEqual(to_markdown("<p>a</p><hr><p>b</p>", main_only=False), "a\n\n---\n\nb")

    def test_table(self):
        html = ("<table><tr><th>A</th><th>B</th></tr>"
                "<tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(to_markdown(html, main_only=False),
                         "| A | B |\n| --- | --- |\n| 1 | 2 |")

    def test_ragged_table_is_padded(self):
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td></tr></table>"
        self.assertIn("| 1 |", to_markdown(html, main_only=False))

    def test_image(self):
        self.assertEqual(to_markdown('<p><img src="/i.png" alt="pic"></p>',
                                     main_only=False), "![pic](/i.png)")

    def test_script_is_dropped(self):
        self.assertEqual(to_markdown("<p>a</p><script>x</script>", main_only=False), "a")

    def test_br_becomes_line_break(self):
        self.assertIn("\n", to_markdown("<p>a<br>b</p>", main_only=False))


class MainContentTests(unittest.TestCase):
    def test_prefers_article_over_nav(self):
        html = ("<body><nav>" + "menu " * 20 + "</nav>"
                "<article>" + "<p>" + "real content " * 20 + "</p>" + "</article></body>")
        self.assertEqual(extract_main(html).tag, "article")

    def test_link_density(self):
        self.assertAlmostEqual(link_density(parse("<div><a>Menu</a> about</div>")), 0.4)

    def test_link_density_empty(self):
        self.assertEqual(link_density(parse("<div> </div>")), 0.0)

    def test_boilerplate_class_is_penalised(self):
        html = ("<body><div class='sidebar'>" + "<p>" + "x " * 200 + "</p></div>"
                "<div class='content'><p>" + "y " * 100 + "</p></div></body>")
        rendered = to_markdown(html)
        self.assertIn("y", rendered)
        self.assertNotIn("x x", rendered)

    def test_falls_back_to_body(self):
        self.assertEqual(extract_main("<body><p>only</p></body>").tag, "body")

    def test_no_candidates_returns_root(self):
        self.assertEqual(extract_main("<p>bare</p>").tag, "#document")

    def test_main_content_strips_markup(self):
        text = main_content("<article><p>Hello <b>world</b></p></article>")
        self.assertEqual(text, "Hello world")


class TextTests(unittest.TestCase):
    def test_blocks_separated(self):
        self.assertEqual(to_text("<h1>T</h1><p>x</p>", main_only=False), "T\n\nx")

    def test_list_items(self):
        self.assertEqual(to_text("<ul><li>a</li><li>b</li></ul>", main_only=False), "a\n\nb")

    def test_skips_boilerplate(self):
        html = "<body><div class='cookie-banner'><p>cookies</p></div><p>text</p></body>"
        self.assertEqual(to_text(html), "text")


class NodeTests(unittest.TestCase):
    def test_iter_is_depth_first(self):
        root = parse("<div><p>a</p></div>")
        tags = [node.tag for node in root.iter()]
        self.assertEqual(tags, ["#document", "div", "p"])

    def test_append_sets_parent(self):
        parent = Node(tag="div")
        child = Node(tag="p")
        parent.append(child)
        self.assertIs(child.parent, parent)


if __name__ == "__main__":
    unittest.main()
