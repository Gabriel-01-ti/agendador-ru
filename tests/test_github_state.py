import base64
import os
import unittest
from datetime import date, datetime
from unittest.mock import patch
import github_state
import weekly
import worker
import scheduled

class GitHubStateTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {'STATE_BACKEND':'github','APP_SECRET':'z'*40,'RU_USER':'fake','RU_PASSWORD':'fake','BOOK_TIME':'15:00','REMINDER_TIME':'09:00','CUTOFF_TIME':'15:55'})
        self.env.start()
        self.row=None
        self.writes=0
        self.conflict=False
        self.mock=patch('github_state.api',side_effect=self.api)
        self.mock.start()
    def tearDown(self):
        self.mock.stop(); self.env.stop()
    def api(self,method='GET',data=None):
        if method=='GET':return self.row
        if self.conflict:raise RuntimeError('Alteração concorrente')
        self.assertEqual(data.get('sha'),self.row['sha'] if self.row else None)
        self.writes+=1
        self.row={'content':data['content'],'sha':str(self.writes)}
        return {}
    def test_preferences_survive_new_connection_and_remain_encrypted(self):
        weekly.set_defaults([0,2])
        raw=base64.b64decode(self.row['content'])
        self.assertNotIn(b'SQLite',raw)
        self.assertEqual(weekly.defaults(),[0,2])
        writes=self.writes
        self.assertEqual(weekly.defaults(),[0,2])
        self.assertEqual(self.writes,writes)
        week=date(2026,10,5)
        weekly.choose(week,[1,4],datetime(2026,10,4,14,tzinfo=weekly.TZ))
        self.assertEqual(weekly.claim(week),['2026-10-06','2026-10-09'])
        self.assertIsNone(weekly.claim(week))
    def test_conflict_prevents_external_reservation(self):
        week=date(2026,10,5)
        weekly.state(week)
        self.conflict=True
        calls=[]
        with self.assertRaises(RuntimeError):
            worker.tick(datetime(2026,10,4,15,tzinfo=weekly.TZ),lambda *args,**kwargs:calls.append(args))
        self.assertEqual(calls,[])
        self.conflict=False
        self.assertIsNone(weekly.state(week)['status'])
    def test_wrong_secret_cannot_reset_or_read_state(self):
        weekly.set_defaults([0])
        writes=self.writes
        with patch.dict(os.environ,{'APP_SECRET':'different-secret'*4}):
            with self.assertRaises(RuntimeError):weekly.defaults()
        self.assertEqual(self.writes,writes)
    def test_check_only_does_not_send_or_book(self):
        with patch.dict(os.environ, {'SCHEDULE_ENABLED':'true','STATE_TOKEN':'fake','CHECK_ONLY':'true'}), patch('worker.tick') as tick:
            self.assertEqual(scheduled.main(),0)
            tick.assert_not_called()
    def test_disabled_schedule_does_not_access_state(self):
        with patch.dict(os.environ, {'SCHEDULE_ENABLED':'false'}), patch('worker.tick') as tick:
            self.assertEqual(scheduled.main(),0)
            tick.assert_not_called()

class WhatsAppTests(unittest.TestCase):
    def test_failure_does_not_expose_key_or_phone(self):
        with patch.dict(os.environ,{'CALLMEBOT_PHONE':'+5551999999999','CALLMEBOT_APIKEY':'private-key','APP_SECRET':'x'*40,'PUBLIC_URL':'https://example.com'}), patch('urllib.request.urlopen',side_effect=Exception('https://example.com/?apikey=private-key')):
            with self.assertRaises(RuntimeError) as error:weekly.send_callmebot(date(2026,10,5))
            self.assertNotIn('private-key',str(error.exception))
            self.assertNotIn('5551999999999',str(error.exception))
