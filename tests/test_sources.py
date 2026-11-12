import json
import tempfile
import unittest
from pathlib import Path

from shovel import sources


STUDENT = json.dumps(
    {
        "aiml-tools-free-gpu-access": {
            "tools": [
                {
                    "name": "Foo",
                    "link": "https://foo.example",
                    "short_desc": "Free GPU",
                    "benefit": "",
                    "verification": "",
                }
            ]
        }
    }
)


class ImportLocalTest(unittest.TestCase):
    def test_reads_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "data.json").write_text(STUDENT, encoding="utf-8")
            items = sources.import_local(
                {"kind": "student_json", "local": "data.json"}, base
            )
            self.assertEqual(len(items), 1)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sources.import_local({"kind": "student_json", "local": "nope.json"}, Path(tmp)), [])

    def test_missing_local_key(self):
        self.assertEqual(sources.import_local({"kind": "student_json"}, Path("/tmp")), [])


class StoreRawTest(unittest.TestCase):
    def test_content_addressed_and_deduped(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp)
            digest_one, ref_one = sources._store_raw("src", "hello", "md", daily, "2026-11-13")
            digest_two, ref_two = sources._store_raw("src", "hello", "md", daily, "2026-11-13")
            self.assertEqual(digest_one, digest_two)
            self.assertEqual(ref_one, ref_two)
            self.assertTrue((daily / "2026-11-13" / ref_one).exists())

    def test_reuses_previous_day_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp)
            digest, ref = sources._store_raw("src", "same", "md", daily, "2026-11-12")
            (daily / "2026-11-12" / "manifest.json").write_text(
                json.dumps({"sources": {"src": {"hash": digest, "raw": ref}}}), encoding="utf-8"
            )
            same_digest, new_ref = sources._store_raw("src", "same", "md", daily, "2026-11-13")
            self.assertEqual(same_digest, digest)
            self.assertEqual(new_ref, "../2026-11-12/raw/src-" + digest + ".md")
            self.assertFalse((daily / "2026-11-13" / "raw").exists())


class SourceExtTest(unittest.TestCase):
    def test_json_for_student(self):
        self.assertEqual(sources._source_ext({"kind": "student_json"}), "json")
        self.assertEqual(sources._source_ext({"kind": "vps_list"}), "md")


if __name__ == "__main__":
    unittest.main()
