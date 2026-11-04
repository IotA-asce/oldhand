from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class PackageLinksTests(unittest.TestCase):
    def test_pypi_readme_links_are_absolute_and_repo_targets_exist(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^\s)]+)\)", readme)
        self.assertGreater(len(links), 20)
        for link in links:
            with self.subTest(link=link):
                url = urlsplit(link)
                self.assertEqual(url.scheme, "https", "Relative links break on PyPI")
                if url.hostname == "github.com" and url.path.startswith(
                        "/IotA-asce/oldhand/blob/main/"):
                    relative = unquote(url.path.removeprefix("/IotA-asce/oldhand/blob/main/"))
                    self.assertTrue((ROOT / relative).is_file(), f"Missing document: {relative}")
                if url.hostname == "raw.githubusercontent.com":
                    self.assertTrue(url.path.startswith("/IotA-asce/oldhand/main/"))
                    relative = unquote(url.path.removeprefix("/IotA-asce/oldhand/main/"))
                    self.assertTrue((ROOT / relative).is_file(), f"Missing asset: {relative}")


if __name__ == "__main__":
    unittest.main()
