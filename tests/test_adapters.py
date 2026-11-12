import json
import unittest

from shovel import adapters


FREE_FOR_DEV = """# free for dev

## Major Cloud Providers

  * [AWS](https://aws.amazon.com) - Cloud platform.
    * 12 months free EC2 t2.micro instance
    * 5 GB S3 object storage

## PaaS

  * [Render](https://render.com) - Static sites.
  * [Koyeb](https://koyeb.com) - Free tier with one container service.

## APIs, Data and ML

  * [AlphaAI](https://alpha.example) - Free image API.
"""

GPU_GRANTS = """# GPU Grants

[Foo GPU](https://foo.example)

```
Foo offers 100 free GPU hours for academic research.
```
"""

AWESOME_GPU = """# Awesome GPU Cloud

## GPU Cloud Marketplaces

- **[Foo](https://foo.example)** `Official` — Free GPU credits for new users.
  - Notes: H100 availability in three regions.

## Other Section

- **[Bar](https://bar.example)** `Official` — Free GPU credits.
"""

STUDENT = json.dumps(
    {
        "cloud-platforms-compute-credits": {
            "tools": [
                {
                    "name": "Student Cloud",
                    "link": "https://student.example",
                    "short_desc": "Free GPU credits",
                    "benefit": "$50 credit",
                    "verification": "Student email required",
                }
            ]
        }
    }
)

DEEP_LEARNING = """# Deep learning in cloud

## Pricing

| Vendor | Website | Pricing | Free |

## Free Trial / Free Credits

| Cloud vendor | Website | Pricing | Free trial |
| --- | --- | --- | --- |
| AWS | [aws](https://aws.amazon.com) | $ | 12 months free EC2 instance |
| Foo | [f](https://foo.example) | varies | free credits |
| Tracker | [t](https://t.example) | price comparison | free |

## Other table

| A | B | C | D |
| --- | --- | --- | --- |
| x | y | z | w |
"""

VPS_LIST = """# Awesome VPS

## VPS (Unmanaged)

- **[Foo](https://foo.example)** – Generous free tier VPS for one month.
- **[Bar](https://bar.example)** – Paid only, no trial.

## Unrelated

- **[Baz](https://baz.example)** – Free GPU credits.
"""


class FreeForDevTest(unittest.TestCase):
    def test_major_cloud_forced_cpu_and_nested(self):
        items = adapters.parse_free_for_dev(FREE_FOR_DEV)
        aws = [item for item in items if item["name"] == "AWS"]
        self.assertEqual(len(aws), 1)
        self.assertEqual(aws[0]["kind"], "cpu")
        self.assertIn("EC2", aws[0]["limits_text"])
        self.assertNotIn("S3 object storage", aws[0]["limits_text"].split("；")[0])

    def test_paas_filtering(self):
        items = adapters.parse_free_for_dev(FREE_FOR_DEV)
        names = {item["name"] for item in items}
        self.assertIn("Koyeb", names)
        self.assertNotIn("Render", names)

    def test_api_section_ignored(self):
        items = adapters.parse_free_for_dev(FREE_FOR_DEV)
        self.assertNotIn("AlphaAI", {item["name"] for item in items})

    def test_source_ref_has_anchor(self):
        items = adapters.parse_free_for_dev(FREE_FOR_DEV)
        aws = next(item for item in items if item["name"] == "AWS")
        self.assertTrue(aws["source_refs"][0].endswith("#major-cloud-providers"))


class GpuGrantsTest(unittest.TestCase):
    def test_code_block_description(self):
        items = adapters.parse_gpu_grants(GPU_GRANTS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "gpu")
        self.assertEqual(items[0]["free_type"], "grant")
        self.assertIn("100 free GPU hours", items[0]["limits_text"])


class AwesomeGpuTest(unittest.TestCase):
    def test_requires_free_evidence(self):
        items = adapters.parse_awesome_gpu_cloud(AWESOME_GPU)
        names = {item["name"] for item in items}
        self.assertIn("Foo", names)
        self.assertNotIn("Bar", names)

    def test_section_hint_and_extra_line(self):
        items = adapters.parse_awesome_gpu_cloud(AWESOME_GPU)
        foo = next(item for item in items if item["name"] == "Foo")
        self.assertEqual(foo["kind"], "gpu")
        self.assertIn("H100", foo["limits_text"])


class StudentJsonTest(unittest.TestCase):
    def test_student_entry(self):
        items = adapters.parse_student_json(STUDENT)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["free_type"], "student")
        self.assertIn("student", item["tags"])
        self.assertEqual(item["eligibility"], "Student email required")

    def test_invalid_json(self):
        self.assertEqual(adapters.parse_student_json("{not json"), [])


class DeepLearningTest(unittest.TestCase):
    def test_only_free_trial_table(self):
        items = adapters.parse_deep_learning(DEEP_LEARNING)
        names = {item["name"] for item in items}
        self.assertIn("AWS", names)
        self.assertNotIn("Tracker", names)
        self.assertNotIn("x", names)

    def test_other_kind_defaults_to_gpu(self):
        items = adapters.parse_deep_learning(DEEP_LEARNING)
        foo = next(item for item in items if item["name"] == "Foo")
        self.assertEqual(foo["kind"], "gpu")


class VpsListTest(unittest.TestCase):
    def test_free_evidence_and_section_filter(self):
        items = adapters.parse_vps_list(VPS_LIST)
        names = {item["name"] for item in items}
        self.assertIn("Foo", names)
        self.assertNotIn("Bar", names)
        self.assertNotIn("Baz", names)


class DispatchTest(unittest.TestCase):
    def test_unknown_kind(self):
        self.assertEqual(adapters.parse_source({"kind": "nope"}, "text"), [])

    def test_dispatch(self):
        items = adapters.parse_source({"kind": "student_json"}, STUDENT)
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
