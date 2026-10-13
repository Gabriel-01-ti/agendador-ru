import os
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch
import weekly
import worker
import scheduled


class SundayNineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'STATE_BACKEND': 'local', 'DATA_DIR': self.tmp.name,
            'APP_SECRET': 'x' * 40, 'RU_USER': 'fake', 'RU_PASSWORD': 'fake',
            'SCHEDULE_ENABLED': 'true', 'STATE_TOKEN': 'fake',
            'REMINDER_ENABLED': 'false', 'BOOK_TIME': '15:00',
            'REMINDER_TIME': '09:00', 'CUTOFF_TIME': '15:55',
            'WAIT_FOR_BOOKING': 'false', 'CHECK_ONLY': 'false',
        })
        self.env.start()
        self.week = date(2026, 10, 19)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def clock(self, hour, minute=0, second=0):
        return datetime(2026, 10, 18, hour, minute, second, tzinfo=weekly.TZ)

    def test_nine_uses_saved_days_ignores_old_render_time_and_never_duplicates(self):
        weekly.set_defaults([0, 2, 4])
        calls = []
        def runner(user, password, days, deadline):
            calls.append(days)
            self.assertEqual(deadline.hour, 15)
            return [{'data': day, 'status': 'ok'} for day in days]
        with patch('weekly.send_reminder') as sender:
            self.assertEqual(worker.tick(self.clock(8, 59), runner), 'antes das 09h')
            self.assertEqual(worker.tick(self.clock(9), runner), 'concluído')
            self.assertEqual(worker.tick(self.clock(12), runner), 'já processada')
            sender.assert_not_called()
        self.assertEqual(calls, [['2026-10-19', '2026-10-21', '2026-10-23']])
        self.assertEqual(weekly.deadline(self.week).hour, 9)

    def test_delayed_runner_still_books_before_cutoff(self):
        self.assertEqual(worker.tick(self.clock(12, 30), lambda u, p, days, deadline:
            [{'data': day, 'status': 'ok'} for day in days]), 'concluído')

    def test_empty_selection_skips_ru_entirely(self):
        weekly.set_defaults([])
        with patch('weekly.send_reminder') as sender:
            self.assertEqual(worker.tick(self.clock(9), lambda *a, **kw: self.fail('reservou')), 'concluído')
            sender.assert_not_called()

    def test_early_runner_waits_to_nine_without_reserving(self):
        with patch('weekly.now', side_effect=[self.clock(8, 59, 50), self.clock(9)]), patch('scheduled.time.sleep') as sleep, patch('worker.tick') as tick:
            scheduled.wait_for_booking()
            sleep.assert_called_once_with(10)
            tick.assert_not_called()

    def test_runner_started_after_nine_does_not_wait(self):
        with patch('weekly.now', return_value=self.clock(9, 5)), patch('scheduled.time.sleep') as sleep:
            scheduled.wait_for_booking()
            sleep.assert_not_called()

    def test_weekday_never_waits_or_books(self):
        with patch('weekly.now', return_value=datetime(2026, 10, 13, 9, tzinfo=weekly.TZ)), patch('scheduled.time.sleep') as sleep, patch('weekly.state') as state:
            scheduled.wait_for_booking()
            self.assertEqual(worker.tick(), 'fora do domingo')
            sleep.assert_not_called()
            state.assert_not_called()

    def test_expired_or_failed_execution_returns_failure_to_actions(self):
        with patch('github_state.configured', return_value=True):
            for result in ['verificar no RU', 'executando', 'prazo encerrado', 'sem credenciais', 'ocupado']:
                with self.subTest(result=result), patch('worker.tick', return_value=result):
                    self.assertEqual(scheduled.main(), 1)

    def test_success_returns_success_to_actions(self):
        with patch('github_state.configured', return_value=True), patch('worker.tick', return_value='concluído'):
            self.assertEqual(scheduled.main(), 0)

    def test_configuration_check_never_waits_sends_or_reserves(self):
        with patch.dict(os.environ, {'CHECK_ONLY': 'true', 'WAIT_FOR_BOOKING': 'true'}), patch('github_state.configured', return_value=True), patch('weekly.defaults', return_value=[0, 2]), patch('scheduled.wait_for_booking') as wait, patch('worker.tick') as tick:
            self.assertEqual(scheduled.main(), 0)
            wait.assert_not_called()
            tick.assert_not_called()

    def test_optional_reminder_and_cutoff_validation(self):
        weekly.validate_schedule()
        for env in [{'CUTOFF_TIME': '09:00'}, {'CUTOFF_TIME': '16:00'}, {'REMINDER_ENABLED': 'true', 'REMINDER_TIME': '09:00'}]:
            with patch.dict(os.environ, env), self.assertRaises(ValueError):
                weekly.validate_schedule()
        with patch.dict(os.environ, {'REMINDER_ENABLED': 'true', 'REMINDER_TIME': '08:00'}):
            weekly.validate_schedule()
