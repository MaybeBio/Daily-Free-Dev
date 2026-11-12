import tempfile
import unittest
from pathlib import Path

from shovel import signals


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Free GPU credits added</title>
    <link href="https://example.com/a"/>
    <updated>2026-11-12T10:00:00Z</updated>
    <summary>New free GPU plan</summary>
  </entry>
</feed>
"""

RSS = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Free VPS trial</title>
  <link>https://example.com/b</link>
  <pubDate>Tue, 12 Nov 2026 10:00:00 GMT</pubDate>
  <description>Short trial</description>
</item></channel></rss>
"""


class ParseTest(unittest.TestCase):
    def test_atom(self):
        records = signals._parse_xml(ATOM)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Free GPU credits added")
        self.assertEqual(records[0]["url"], "https://example.com/a")
        self.assertEqual(records[0]["published_at"], "2026-11-12T10:00:00Z")

    def test_rss(self):
        records = signals._parse_xml(RSS)
        self.assertEqual(records[0]["url"], "https://example.com/b")
        self.assertTrue(records[0]["published_at"].startswith("2026-11-12"))

    def test_malformed(self):
        self.assertEqual(signals._parse_xml("<not xml"), [])

    def test_hn(self):
        body = '{"hits":[{"title":"Free GPU","url":"https://x.example","created_at":"2026-11-12T10:00:00Z"}]}'
        records = signals._parse_hn(body)
        self.assertEqual(records[0]["title"], "Free GPU")
        self.assertEqual(records[0]["url"], "https://x.example")

    def test_hn_fallback_url(self):
        records = signals._parse_hn('{"hits":[{"title":"Ask","objectID":"42","created_at":""}]}')
        self.assertIn("id=42", records[0]["url"])

    def test_html_cleanup(self):
        self.assertEqual(signals._clean("<p>Hello &amp; <b>world</b></p>"), "Hello & world")


class MatchesTest(unittest.TestCase):
    def test_keyword_hit(self):
        self.assertEqual(signals._matches("Free GPU", ["free", "gpu"], []), ["free", "gpu"])

    def test_exclude_wins(self):
        self.assertEqual(signals._matches("free job", ["free"], ["job"]), [])

    def test_case_insensitive(self):
        self.assertEqual(signals._matches("FREE GPU", ["gpu"], []), ["gpu"])


class IngestTest(unittest.TestCase):
    def test_dedupe_and_cap(self):
        config = {
            "keywords": ["free"],
            "exclude": [],
            "max_per_day": 1,
            "feeds": [
                {"id": "a", "kind": "rss", "url": "https://a.example", "enabled": True},
                {"id": "b", "kind": "rss", "url": "https://b.example", "enabled": True},
            ],
        }

        def transport(method, url, timeout, headers, data):
            body = ATOM if "a.example" in url else RSS
            return 200, body, {}

        with tempfile.TemporaryDirectory() as tmp:
            signal_dir = Path(tmp)
            records = signals.ingest(config, signal_dir=signal_dir, transport=transport)
            self.assertEqual(len(records), 1)
            files = list(signal_dir.glob("*.jsonl"))
            self.assertEqual(len(files), 1)
            self.assertEqual(len(files[0].read_text(encoding="utf-8").splitlines()), 1)

    def test_failed_feed_skipped(self):
        config = {
            "keywords": ["free"],
            "max_per_day": 10,
            "feeds": [{"id": "a", "kind": "rss", "url": "https://a.example"}],
        }

        def transport(method, url, timeout, headers, data):
            return 500, "", {}

        with tempfile.TemporaryDirectory() as tmp:
            records = signals.ingest(config, signal_dir=Path(tmp), transport=transport)
            self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
