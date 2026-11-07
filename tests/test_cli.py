import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from htmltotext.cli import main

PAGE = """<html><body>
<nav class="site-nav"><a href="/">Home</a><a href="/x">Products</a></nav>
<article class="post">
  <h1>Why extraction is hard</h1>
  <p>Boilerplate dominates most pages, so naive text scrapers return menus.</p>
  <ul><li>First point</li><li>Second point</li></ul>
</article>
<footer class="site-footer">Copyright 2026</footer>
</body></html>"""


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(args)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "page.html"
        self.path.write_text(PAGE, encoding="utf-8")

    def test_markdown_keeps_the_article(self):
        code, out, _ = run(["markdown", str(self.path)])
        self.assertEqual(code, 0)
        self.assertIn("# Why extraction is hard", out)
        self.assertIn("- First point", out)

    def test_markdown_drops_navigation(self):
        code, out, _ = run(["markdown", str(self.path)])
        self.assertEqual(code, 0)
        self.assertNotIn("Products", out)
        self.assertNotIn("Copyright 2026", out)

    def test_whole_document_keeps_boilerplate(self):
        _, out, _ = run(["markdown", str(self.path), "--whole-document"])
        self.assertIn("Copyright 2026", out)

    def test_text_mode_has_no_markdown_markers(self):
        _, out, _ = run(["text", str(self.path)])
        self.assertIn("Why extraction is hard", out)
        self.assertNotIn("# Why", out)

    def test_audit_json_reports_container(self):
        code, out, _ = run(["audit", str(self.path), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload[0]["class"], "post")
        self.assertGreater(payload[0]["characters"], 40)

    def test_output_file(self):
        target = Path(self.tmp.name) / "out.md"
        code, _, err = run(["markdown", str(self.path), "-o", str(target)])
        self.assertEqual(code, 0)
        self.assertIn("wrote", err)
        self.assertIn("Why extraction is hard", target.read_text(encoding="utf-8"))

    def test_missing_file_is_reported(self):
        with self.assertRaises(SystemExit):
            run(["markdown", str(Path(self.tmp.name) / "nope.html")])


if __name__ == "__main__":
    unittest.main()
