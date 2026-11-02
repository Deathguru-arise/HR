import unittest

from training.tagging import annotate_span, tag_exact_words


class TaggingTest(unittest.TestCase):
    def test_annotate_span_marks_bio(self):
        tokens = ["Rajesh", "Kumar", "works", "at", "Google"]
        labels = ["O"] * len(tokens)
        annotate_span(tokens, labels, "Rajesh Kumar", "NAME")
        self.assertEqual(labels[:2], ["B-NAME", "I-NAME"])

    def test_tag_exact_words_matches_punctuation(self):
        tokens = ["Python,", "SQL", "Docker"]
        labels = ["O", "O", "O"]
        tag_exact_words(tokens, labels, "Python", "SKILL")
        self.assertEqual(labels[0], "B-SKILL")


if __name__ == "__main__":
    unittest.main()
