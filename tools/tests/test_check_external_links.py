from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "check_external_links.py"
SPEC = importlib.util.spec_from_file_location("check_external_links", SCRIPT)
link_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(link_check)


class LinkCheckTests(unittest.TestCase):
    def test_extract_urls_deduplicates_and_skips_reserved_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "https://docs.uipath.com/path https://docs.uipath.com/path "
                "https://example.com/fixture\n",
                encoding="utf-8",
            )

            self.assertEqual(
                ["https://docs.uipath.com/path"],
                link_check.extract_urls(link_check.text_files(root)),
            )

    def test_authentication_response_counts_as_reachable(self):
        error = HTTPError("https://service.example.net", 403, "Forbidden", {}, None)
        with mock.patch.object(link_check, "request_url", side_effect=error):
            self.assertIsNone(link_check.check_url("https://service.example.net"))

    def test_missing_page_fails(self):
        error = HTTPError("https://service.example.net/missing", 404, "Not Found", {}, None)
        with mock.patch.object(link_check, "request_url", side_effect=error):
            self.assertEqual(
                "https://service.example.net/missing: HTTP 404",
                link_check.check_url("https://service.example.net/missing"),
            )


if __name__ == "__main__":
    unittest.main()
