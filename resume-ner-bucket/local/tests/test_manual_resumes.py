import unittest

from training.manual_resumes import build_manual_examples, TEMPLATES


class ManualResumesTest(unittest.TestCase):
    def test_manual_examples_unique(self):
        examples = build_manual_examples()
        keys = {(tuple(example["tokens"]), tuple(example["ner_tags"])) for example in examples}
        self.assertEqual(len(keys), len(examples))
        self.assertEqual(len(examples), len(TEMPLATES))


if __name__ == "__main__":
    unittest.main()
