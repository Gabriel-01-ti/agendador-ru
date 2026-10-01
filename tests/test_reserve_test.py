import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, date
from unittest.mock import patch
import weekly
import reserve_test

class ReservationTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name,'STATE_BACKEND':'local','STATE_TOKEN':'fake','APP_SECRET':'x'*40,'RU_USER':'fake','RU_PASSWORD':'fake','TEST_RESERVATION_DATE':'2026-10-05'})
        self.env.start()
        self.clock=patch('weekly.now',return_value=datetime(2026,10,1,19,22,tzinfo=weekly.TZ));self.clock.start()
    def tearDown(self):
        self.clock.stop();self.env.stop();self.tmp.cleanup()
    def run_test(self,runner):
        with patch('reserve_test.github_state.configured',return_value=True), patch('weekly.db',side_effect=self.local_db):
            return reserve_test.main(runner)
    @contextmanager
    def local_db(self):
        with patch('github_state.configured',return_value=False), self.original_db() as conn:
            yield conn
    original_db=staticmethod(weekly.db)
    def test_real_single_date_can_run_thursday_evening_and_never_sends_whatsapp(self):
        calls=[]
        def runner(user,password,days):calls.append((user,password,days));return [{'data':days[0],'status':'ok'}]
        with patch('weekly.send_reminder') as sender:
            self.assertEqual(self.run_test(runner),0)
            sender.assert_not_called()
        self.assertEqual(calls,[('fake','fake',['2026-10-05'])])
        self.assertEqual(weekly.reservation_test_history()[0]['status'],'concluído')
        self.assertEqual(self.run_test(lambda *a:self.fail('duplicou')),1)
        self.assertNotIn('2026-10-05',weekly.claim(date(2026,10,5)))
    def test_failure_is_saved_and_not_retried(self):
        def fail(*a):raise RuntimeError('private')
        self.assertEqual(self.run_test(fail),1)
        self.assertEqual(weekly.reservation_test_history()[0]['status'],'verificar no RU')
        self.assertEqual(self.run_test(lambda *a:self.fail('duplicou')),1)
    def test_reject_invalid_today_past_and_weekend_before_claim(self):
        for day in ['bad','2026-10-01','2026-09-30','2026-10-03']:
            with patch.dict(os.environ,{'TEST_RESERVATION_DATE':day}):
                self.assertEqual(self.run_test(lambda *a:self.fail('reservou')),1)
        self.assertEqual(weekly.reservation_test_history(),[])
    def test_durable_claim_failure_blocks_external_request(self):
        with patch('weekly.claim_reservation_test',side_effect=RuntimeError('conflict')):
            self.assertEqual(self.run_test(lambda *a:self.fail('reservou sem persistir')),1)
    def test_previously_started_week_is_not_repeated_by_test(self):
        weekly.claim(date(2026,10,5))
        self.assertEqual(self.run_test(lambda *a:self.fail('duplicou semana')),1)
