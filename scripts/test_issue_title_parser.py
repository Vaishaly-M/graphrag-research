"""Offline regressions for delimited issue titles."""
import unittest

from src.systems.query_registry import match_registered_query


class IssueTitleParserTests(unittest.TestCase):
    def test_preserves_title_contents(self):
        for title in (
            "Can't find API Getway project",
            "Users' settings aren't saved",
            'Cannot load "API" project',
            "Failure in repository other/project",
            "Ordinary title",
        ):
            for delimiter in ("'", '"'):
                with self.subTest(title=title, delimiter=delimiter):
                    question = (
                        f"What is the issue number for {delimiter}{title}{delimiter} "
                        "in repository dotnet/eShop?"
                    )
                    match = match_registered_query(question)
                    self.assertIsNotNone(match)
                    self.assertEqual(match.params, {"repo": "dotnet/eShop", "title": title})
                    self.assertEqual(match.route, "graph")

    def test_rejects_unclosed_title(self):
        self.assertIsNone(match_registered_query(
            "What is the issue number for 'Unclosed in repository dotnet/eShop?"
        ))


if __name__ == "__main__":
    unittest.main()
