import os
import tempfile
import unittest
from datetime import datetime, date
from unittest.mock import patch
import weekly
import worker

class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'DATA_DIR': self.tmp.name, 'APP_SECRET': 'x'*40, 'RU_USER': 'fake', 'RU_PASSWORD': 'fake', 'BOOK_TIME': '15:00', 'REMINDER_TIME': '09:00', 'CUTOFF_TIME': '15:55'})
        self.env.start()
        self.week = date(2026,10,5)
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def clock(self, hour, minute=0):
        return datetime(2026,10,4,hour,minute,tzinfo=weekly.TZ)
    def test_token_and_cutoff(self):
        token = weekly.token(self.week)
        self.assertEqual(weekly.token_week(token,self.clock(14)),self.week)
        for value, clock in [(token+'x',self.clock(14)),(token,self.clock(15))]:
            with self.assertRaises(ValueError): weekly.token_week(value,clock)
    def test_default_and_override(self):
        weekly.set_defaults([0,2,4])
        weekly.choose(self.week,[1,3],self.clock(14))
        self.assertEqual(weekly.claim(self.week), ['2026-10-06','2026-10-08'])
        self.assertIsNone(weekly.claim(self.week))
        with self.assertRaises(ValueError): weekly.choose(self.week,[0],self.clock(14))
    def test_empty_choice_does_not_fall_back(self):
        weekly.choose(self.week,[],self.clock(14))
        self.assertEqual(weekly.claim(self.week),[])
    def test_reminder_only_once_and_reservation_timing(self):
        calls=[]; messages=[]
        def sender(w): messages.append(w); return 'aceito'
        def runner(user,password,dates,deadline):
            calls.append(dates)
            return [{'data':d,'status':'ok'} for d in dates]
        worker.tick(self.clock(8),runner,sender)
        worker.tick(self.clock(9),runner,sender)
        worker.tick(self.clock(14),runner,sender)
        self.assertEqual(len(messages),1)
        self.assertEqual(calls,[])
        worker.tick(self.clock(15),runner,sender)
        worker.tick(self.clock(15,1),runner,sender)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],'2026-10-05')
        self.assertEqual(weekly.state(self.week)['status'],'concluído')
    def test_after_cutoff_does_not_run(self):
        worker.tick(self.clock(15,55),lambda *a,**k:self.fail('executou tarde'))
        self.assertIsNone(weekly.state(self.week)['status'])
    def test_failure_no_duplicate(self):
        def fail(*a,**k): raise RuntimeError('fake')
        worker.tick(self.clock(15),fail)
        self.assertEqual(weekly.state(self.week)['status'],'verificar no RU')
        worker.tick(self.clock(15,1),lambda *a,**k:self.fail('duplicou'))
    def test_restart_does_not_repeat_claimed_week(self):
        weekly.claim(self.week)
        worker.tick(self.clock(15),lambda *a,**k:self.fail('repetiu após reiniciar'))
    def test_days_validation(self):
        for days in [None, '012', [True],[-1],[5]]:
            with self.assertRaises(ValueError): weekly.validate_days(days)
    def test_execution_lock_shared(self):
        with weekly.execution_lock():
            with self.assertRaises(RuntimeError):
                with weekly.execution_lock(): pass

if __name__ == '__main__': unittest.main()
