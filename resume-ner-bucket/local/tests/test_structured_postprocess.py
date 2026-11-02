import unittest

from training.labels import LABEL2ID
from training.structured_postprocess import StructuredPostProcessor, build_text_and_spans


class StructuredPostprocessTest(unittest.TestCase):
    def test_build_text_and_spans_round_trip(self):
        tokens = ["Jane", "Doe", "jane@example.com", "|", "+1", "5551234567", "|", "Seattle,", "WA"]
        tags = [
            LABEL2ID["B-NAME"],
            LABEL2ID["I-NAME"],
            LABEL2ID["B-EMAIL"],
            LABEL2ID["O"],
            LABEL2ID["B-PHONE"],
            LABEL2ID["I-PHONE"],
            LABEL2ID["O"],
            LABEL2ID["B-LOCATION"],
            LABEL2ID["I-LOCATION"],
        ]
        text, spans = build_text_and_spans(tokens, tags, {v: k for k, v in LABEL2ID.items()})
        self.assertEqual(text, "Jane Doe jane@example.com | +1 5551234567 | Seattle, WA")
        self.assertEqual(
            [(span.label, span.text) for span in spans],
            [
                ("NAME", "Jane Doe"),
                ("EMAIL", "jane@example.com"),
                ("PHONE", "+1 5551234567"),
                ("LOCATION", "Seattle, WA"),
            ],
        )

    def test_structured_postprocess_builds_expected_fields(self):
        processor = StructuredPostProcessor(".")
        text, spans = build_text_and_spans(
            [
                "Jane",
                "Doe",
                "jane@example.com",
                "+1",
                "5551234567",
                "Seattle,",
                "WA",
                "Engineer",
                "Acme",
                "January",
                "2020",
                "Present",
            ],
            [
                LABEL2ID["B-NAME"],
                LABEL2ID["I-NAME"],
                LABEL2ID["B-EMAIL"],
                LABEL2ID["B-PHONE"],
                LABEL2ID["I-PHONE"],
                LABEL2ID["B-LOCATION"],
                LABEL2ID["I-LOCATION"],
                LABEL2ID["B-TITLE"],
                LABEL2ID["B-COMPANY"],
                LABEL2ID["B-DATE"],
                LABEL2ID["I-DATE"],
                LABEL2ID["B-DATE"],
            ],
            {v: k for k, v in LABEL2ID.items()},
        )
        parsed = processor.build_structured_resume_from_spans(spans, text)
        self.assertEqual(parsed["personal"]["name"], "Jane Doe")
        self.assertEqual(parsed["personal"]["email"], "jane@example.com")
        self.assertEqual(parsed["experience"][0]["title"], "Engineer")
        self.assertEqual(parsed["experience"][0]["company"], "Acme")
        self.assertEqual(parsed["experience"][0]["start_date"], "January 2020")
        self.assertEqual(parsed["experience"][0]["end_date"], "Present")

    def test_normalizes_skills_and_certifications(self):
        processor = StructuredPostProcessor(".")
        self.assertEqual(processor.normalize_skill("node js"), "node.js")
        self.assertEqual(processor.normalize_skill("cpp"), "c++")
        self.assertEqual(processor.normalize_certification("ServSafe Manager"), "servsafe manager certification")

    def test_compute_years_uses_floor(self):
        processor = StructuredPostProcessor(".")
        years = processor.compute_years([
            {"start_date": "January 2020", "end_date": "June 2022"},
        ])
        self.assertEqual(years, 2)


if __name__ == "__main__":
    unittest.main()
