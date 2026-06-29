from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.notes import NoteRequest, create_note, delete_note, load_notes, update_note  # noqa: E402


class NotesTest(unittest.TestCase):
    def test_create_update_and_delete_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))

            created = create_note(NoteRequest(title="Decision log", content="# Trim plan"), settings)
            updated = update_note(created.id, NoteRequest(title="Decision log", content="# Updated"), settings)
            notes = load_notes(settings)
            deleted = delete_note(created.id, settings)
            remaining = load_notes(settings)

        self.assertIsNotNone(updated)
        self.assertEqual(notes[0].title, "Decision log")
        self.assertEqual(notes[0].content, "# Updated")
        self.assertTrue(deleted)
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
