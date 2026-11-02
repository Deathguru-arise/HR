import unittest

from training.dataset_utils import dedupe_examples, stable_split_examples


class DatasetUtilsTest(unittest.TestCase):
    def test_dedupe_examples_removes_exact_duplicates(self):
        example = {"tokens": ["A"], "ner_tags": [0], "metadata": {"group_id": "x"}}
        unique, removed = dedupe_examples([example, dict(example)])
        self.assertEqual(len(unique), 1)
        self.assertEqual(removed, 1)

    def test_stable_split_keeps_group_together(self):
        examples = [
            {"tokens": ["A"], "ner_tags": [0], "metadata": {"group_id": "same"}},
            {"tokens": ["B"], "ner_tags": [0], "metadata": {"group_id": "same"}},
            {"tokens": ["C"], "ner_tags": [0], "metadata": {"group_id": "other"}},
        ]
        train, val = stable_split_examples(examples, train_ratio=0.5)
        sides = []
        if any(example["metadata"]["group_id"] == "same" for example in train):
            sides.append("train")
        if any(example["metadata"]["group_id"] == "same" for example in val):
            sides.append("val")
        self.assertEqual(len(sides), 1)


if __name__ == "__main__":
    unittest.main()
