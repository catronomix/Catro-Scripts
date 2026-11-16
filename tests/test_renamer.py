# Focused tests for renamer sorting methods
"""
			RENAME SORTING TESTS
			====================
Creation-date sorting must use filesystem creation timestamps independently
from the existing modification-date sorting.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import renamer  # noqa: E402


class CreationDateSortingTests(unittest.TestCase):
	"""Verify both creation-date sort directions."""

	def test_creation_date_sorting(self):
		files = ["new.txt", "old.txt", "middle.txt"]
		created = {"old.txt": 10, "middle.txt": 20, "new.txt": 30}

		def getctime(path):
			return created[os.path.basename(path)]

		with patch.object(renamer.os.path, "getctime", side_effect=getctime):
			self.assertEqual(
				renamer.sort_files("folder", files[:], "cdate_asc"),
				["old.txt", "middle.txt", "new.txt"],
			)
			self.assertEqual(
				renamer.sort_files("folder", files[:], "cdate_desc"),
				["new.txt", "middle.txt", "old.txt"],
			)

