import unittest

from shovel import classify


class IsComputeTest(unittest.TestCase):
    def test_gpu_credit(self):
        self.assertTrue(classify.is_compute("Free GPU credits for new users"))

    def test_cloud_server(self):
        self.assertTrue(classify.is_compute("Free cloud server for 12 months"))

    def test_kubernetes(self):
        self.assertTrue(classify.is_compute("Managed Kubernetes with free control plane"))

    def test_database_rejected(self):
        self.assertFalse(classify.is_compute("Free PostgreSQL database hosting"))

    def test_object_storage_rejected(self):
        self.assertFalse(classify.is_compute("10 GB free object storage"))

    def test_evernote_rejected(self):
        self.assertFalse(classify.is_compute("Notebook - free Evernote alternative"))

    def test_plain_web_service_rejected(self):
        self.assertFalse(classify.is_compute("Free static site hosting and forms"))

    def test_compute_rescues_blacklisted(self):
        self.assertTrue(classify.is_compute("GPU compute with object storage included"))


class FreeEvidenceTest(unittest.TestCase):
    def test_free_tier(self):
        self.assertTrue(classify.has_free_evidence("generous free tier"))

    def test_free_speech_rejected(self):
        self.assertFalse(classify.has_free_evidence("free speech platform"))

    def test_trusted_source_bypasses_evidence(self):
        self.assertTrue(classify.has_free_evidence("paid only", "free-for-dev"))


class FreeTypeTest(unittest.TestCase):
    def test_permanent(self):
        self.assertEqual(classify.classify_free_type("free forever"), "permanent")

    def test_renewable(self):
        self.assertEqual(classify.classify_free_type("monthly credits that renew"), "renewable")

    def test_trial(self):
        self.assertEqual(classify.classify_free_type("$100 free credits on signup"), "trial_credit")

    def test_grant(self):
        self.assertEqual(classify.classify_free_type("research grant for academics"), "grant")

    def test_student(self):
        self.assertEqual(classify.classify_free_type("free for students with .edu"), "student")

    def test_default(self):
        self.assertEqual(classify.classify_free_type("some offer"), "permanent")


class AccessTest(unittest.TestCase):
    def test_no_card(self):
        access = classify.access_from_text("no credit card required")
        self.assertEqual(access["card"], "not_required")

    def test_card_required(self):
        access = classify.access_from_text("credit card required for verification")
        self.assertEqual(access["card"], "required")

    def test_phone(self):
        access = classify.access_from_text("phone verification required")
        self.assertEqual(access["phone"], "required")

    def test_unknown(self):
        access = classify.access_from_text("free tier")
        self.assertEqual(access, {"card": "unknown", "phone": "unknown", "realname": "unknown"})


class TagsTest(unittest.TestCase):
    def test_trial_and_gpu_tag(self):
        tags = classify.infer_tags("free H100 trial", "gpu", "trial_credit")
        self.assertIn("trial", tags)
        self.assertIn("h100", tags)

    def test_needs_review(self):
        self.assertIn("needs-review", classify.infer_tags("thing", "other", "permanent"))


if __name__ == "__main__":
    unittest.main()
