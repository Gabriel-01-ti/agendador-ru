import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import requested
import weekly


class RequestedTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'request.json'
        self.path.write_text(json.dumps({'target_week': '2026-10-19'}), encoding='utf-8')

    def tearDown(self):
        self.folder.cleanup()

    def test_current_sunday_uses_shared_scheduler(self):
        clock = datetime(2026, 10, 18, 10, 46, tzinfo=weekly.TZ)
        with patch('weekly.now', return_value=clock), patch('scheduled.main', return_value=0) as run:
            self.assertEqual(requested.main(self.path), 0)
            run.assert_called_once_with()

    def test_scheduler_failure_is_not_reported_as_success(self):
        clock = datetime(2026, 10, 18, 10, 46, tzinfo=weekly.TZ)
        with patch('weekly.now', return_value=clock), patch('scheduled.main', return_value=1):
            self.assertEqual(requested.main(self.path), 1)

    def test_old_request_cannot_book_a_different_week(self):
        clock = datetime(2026, 10, 25, 9, tzinfo=weekly.TZ)
        with patch('weekly.now', return_value=clock), patch('scheduled.main') as run:
            self.assertEqual(requested.main(self.path), 1)
            run.assert_not_called()

    def test_weekday_cannot_start_a_reservation(self):
        clock = datetime(2026, 10, 19, 9, tzinfo=weekly.TZ)
        with patch('weekly.now', return_value=clock), patch('scheduled.main') as run:
            self.assertEqual(requested.main(self.path), 1)
            run.assert_not_called()

    def test_invalid_request_cannot_start_a_reservation(self):
        clock = datetime(2026, 10, 18, 9, tzinfo=weekly.TZ)
        for text in ['bad', '[]', '{}']:
            with self.subTest(text=text):
                self.path.write_text(text, encoding='utf-8')
                with patch('weekly.now', return_value=clock), patch('scheduled.main') as run:
                    self.assertEqual(requested.main(self.path), 1)
                    run.assert_not_called()
