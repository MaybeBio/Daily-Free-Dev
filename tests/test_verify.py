import unittest

from shovel import verify


def transport(code, body="", headers=None):
    def call(method, url, timeout, extra_headers, data):
        return code, body, headers or {}

    return call


SUB = {"id": "x", "name": "X", "official_url": "https://x.example", "homepage": "https://x.example"}


class CheckResourceTest(unittest.TestCase):
    def test_online_with_keyword(self):
        result = verify.check_resource(SUB, 1, transport(200, "Start with $100 free credits"))
        self.assertEqual(result["status"], "online")
        self.assertTrue(result["keyword_hit"])

    def test_suspect_without_keyword(self):
        result = verify.check_resource(SUB, 1, transport(200, "Enterprise pricing"))
        self.assertEqual(result["status"], "suspect")

    def test_blocked(self):
        self.assertEqual(verify.check_resource(SUB, 1, transport(403))["status"], "blocked")

    def test_gone(self):
        self.assertEqual(verify.check_resource(SUB, 1, transport(404))["status"], "gone")

    def test_error_on_network(self):
        self.assertEqual(verify.check_resource(SUB, 1, transport(0))["status"], "error")

    def test_error_on_5xx(self):
        self.assertEqual(verify.check_resource(SUB, 1, transport(503))["status"], "error")

    def test_missing_url(self):
        result = verify.check_resource({"id": "x"}, 1, transport(200, "free"))
        self.assertEqual(result["status"], "unknown")

    def test_final_url_header(self):
        result = verify.check_resource(SUB, 1, transport(200, "free", {"X-Final-URL": "https://y.example"}))
        self.assertEqual(result["final_url"], "https://y.example")


class RunVerifyTest(unittest.TestCase):
    def test_streak_increments_and_resets(self):
        resources = [dict(SUB)]
        previous = {"resources": {"x": {"streak_gone": 2}}}
        result = verify.run_verify(
            resources,
            previous=previous,
            workers=1,
            transport=transport(404),
            jitter=0,
        )
        self.assertEqual(result["resources"]["x"]["streak_gone"], 3)
        self.assertEqual(result["summary"], {"gone": 1})

        healthy = verify.run_verify(
            [dict(SUB)],
            previous={"resources": {"x": {"streak_gone": 5}}},
            workers=1,
            transport=transport(200, "free"),
            jitter=0,
        )
        self.assertEqual(healthy["resources"]["x"]["streak_gone"], 0)

    def test_only_filter(self):
        resources = [{"id": "a", "homepage": "https://a.example"}, {"id": "b", "homepage": "https://b.example"}]
        result = verify.run_verify(
            resources,
            only={"b"},
            workers=1,
            transport=transport(200, "free"),
            jitter=0,
        )
        self.assertEqual(set(result["resources"]), {"b"})


if __name__ == "__main__":
    unittest.main()
