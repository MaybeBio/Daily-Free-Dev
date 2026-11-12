import unittest

from shovel import registry


def make(name, url, **extra):
    item = {
        "name": name,
        "homepage": url,
        "official_url": url,
        "kind": "gpu",
        "free_type": "permanent",
        "tags": [],
        "source_refs": ["https://src.example"],
        "verified_at": "2026-01-01",
    }
    item.update(extra)
    return item


class NormalizeUrlTest(unittest.TestCase):
    def test_strips_utm_and_www_and_slash(self):
        value = registry.normalize_url("https://www.Example.com/path/?utm_source=x&a=1")
        self.assertEqual(value, "https://example.com/path?a=1")

    def test_adds_scheme(self):
        self.assertEqual(registry.normalize_url("example.com/x"), "https://example.com/x")

    def test_empty(self):
        self.assertEqual(registry.normalize_url("  "), "")


class MergeTest(unittest.TestCase):
    def test_dedupe_by_url(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example/")],
            [make("Foo Alt", "https://foo.example")],
        )
        self.assertEqual(len(merged), 1)

    def test_dedupe_by_name(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example")],
            [make("Foo", "https://foo-new.example")],
        )
        self.assertEqual(len(merged), 1)

    def test_fill_empty_and_upgrade_kind(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example", kind="other", limits_text="")],
            [make("Foo", "https://foo.example", kind="gpu", limits_text="100 hours")],
        )
        self.assertEqual(merged[0]["kind"], "gpu")
        self.assertEqual(merged[0]["limits_text"], "100 hours")

    def test_existing_non_empty_wins(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example", limits_text="keep me")],
            [make("Foo", "https://foo.example", limits_text="new text")],
        )
        self.assertEqual(merged[0]["limits_text"], "keep me")

    def test_unions_tags_and_sources(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example", tags=["gpu"], source_refs=["a"])],
            [make("Foo", "https://foo.example", tags=["trial"], source_refs=["b"])],
        )
        self.assertEqual(merged[0]["tags"], ["gpu", "trial"])
        self.assertEqual(merged[0]["source_refs"], ["a", "b"])

    def test_keeps_latest_verified_at(self):
        merged = registry.merge_resources(
            [make("Foo", "https://foo.example", verified_at="2026-01-01")],
            [make("Foo", "https://foo.example", verified_at="2026-05-01")],
        )
        self.assertEqual(merged[0]["verified_at"], "2026-05-01")

    def test_disjoint_ids_unique(self):
        merged = registry.merge_resources(
            [{"id": "foo", "name": "Foo", "homepage": "https://a.example"}],
            [{"id": "foo", "name": "Bar", "homepage": "https://b.example"}],
        )
        ids = [item["id"] for item in merged]
        self.assertEqual(len(ids), len(set(ids)))


class CanonicalTest(unittest.TestCase):
    def test_sorted_and_deduped(self):
        lines = registry.canonical_lines(
            [make("B", "https://b.example"), make("A", "https://a.example"), make("A", "https://a.example")]
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines, sorted(lines))

    def test_limits_are_truncated(self):
        lines = registry.canonical_lines([make("A", "https://a.example", limits_text="x" * 400)])
        self.assertEqual(lines[0].rsplit(" | ", 1)[-1], "x" * 300)


class BuildRegistryTest(unittest.TestCase):
    def test_status_overlay_and_stale(self):
        status = {
            "resources": {
                "foo": {"status": "gone", "streak_gone": 3, "checked_at": "2026-01-01T00:00:00Z"},
            }
        }
        item = registry.normalize_resource(make("Foo", "https://foo.example"))
        built = registry.build_registry([item], status)
        record = built["resources"][0]
        self.assertEqual(record["status"], "gone")
        self.assertTrue(record.get("stale"))
        self.assertEqual(built["stats"]["resources"], 1)

    def test_counts(self):
        built = registry.build_registry(
            [
                registry.normalize_resource(make("A", "https://a.example", kind="gpu")),
                registry.normalize_resource(make("B", "https://b.example", kind="vps")),
            ]
        )
        self.assertEqual(built["stats"]["kinds"], {"gpu": 1, "vps": 1})
        self.assertEqual(built["stats"]["statuses"], {"unknown": 2})


if __name__ == "__main__":
    unittest.main()
