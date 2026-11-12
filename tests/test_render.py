import json
import re
import tempfile
import unittest
from pathlib import Path

from shovel import render


REGISTRY = {
    "updated_at": "2026-11-13T00:00:00Z",
    "stats": {"resources": 1, "kinds": {"gpu": 1}, "free_types": {"permanent": 1}, "statuses": {"online": 1}},
    "resources": [
        {
            "id": "foo",
            "name": "Foo",
            "provider": "Foo Inc",
            "kind": "gpu",
            "free_type": "permanent",
            "tags": ["gpu"],
            "limits_text": "100 GPU hours",
            "eligibility": "",
            "homepage": "https://foo.example",
            "official_url": "https://foo.example",
            "status": "online",
        }
    ],
}


class ReadmeTest(unittest.TestCase):
    def test_guard_skips_handwritten_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text("# my notes\n", encoding="utf-8")
            result = render.render_readme(REGISTRY, path)
            self.assertEqual(result.name, "README.generated.md")
            self.assertEqual(path.read_text(encoding="utf-8"), "# my notes\n")
            self.assertIn(render.GENERATED_MARKER, result.read_text(encoding="utf-8"))

    def test_generated_marker_allows_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(render.GENERATED_MARKER + "\nold\n", encoding="utf-8")
            result = render.render_readme(REGISTRY, path)
            self.assertEqual(result, path)
            self.assertIn("每日免费算力资源清单", result.read_text(encoding="utf-8"))

    def test_feed_link_is_valid_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            render.render_readme(REGISTRY, path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("site/feed.xml", content)
            self.assertNotIn("site/index.htmlfeed.xml", content)


class CsvTest(unittest.TestCase):
    def test_header_and_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resources.csv"
            render.render_csv(REGISTRY, path)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], ",".join(render.CSV_FIELDS))
            self.assertIn("Foo", lines[1])
            self.assertEqual(len(lines), 2)


class FeedTest(unittest.TestCase):
    def test_escapes_and_rfc822(self):
        changes = [{"at": "2026-11-13T00:00:00Z", "source": "s", "name": "A&B", "added_count": 1, "removed_count": 0, "added": ["u | N<1>"]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.xml"
            render.render_feed(changes, path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("A&amp;B", content)
            self.assertIn("N&lt;1&gt;", content)
            self.assertIn("+1 / -0", content)
            self.assertIn("Fri, 13 Nov 2026", content)


class SiteTest(unittest.TestCase):
    def test_payload_is_valid_json_and_escaped(self):
        registry = json.loads(json.dumps(REGISTRY))
        registry["resources"][0]["limits_text"] = "</script><b>x</b>"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            render.render_site(registry, [{"title": "sig"}], path)
            content = path.read_text(encoding="utf-8")
            payload = re.search(r'<script id="payload" type="application/json">(.*?)</script>', content, re.S).group(1)
            self.assertNotIn("</script>", payload)
            data = json.loads(payload)
            self.assertEqual(data["resources"][0]["name"], "Foo")
            self.assertEqual(data["signals"][0]["title"], "sig")
            self.assertEqual(data["labels"]["kind"]["gpu"], "GPU")


if __name__ == "__main__":
    unittest.main()
