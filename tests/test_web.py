import base64
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime
import weekly
from app import app

class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name,'APP_SECRET':'s'*40,'ADMIN_PASSWORD':'admin-secret-123456','STATE_BACKEND':'local','AUTOMATION_ENABLED':'true'})
        self.env.start()
        self.client=app.test_client()
        self.headers={'Authorization':'Basic '+base64.b64encode(b'admin:admin-secret-123456').decode()}
    def tearDown(self): self.env.stop();self.tmp.cleanup()
    def test_private_panel_and_public_health(self):
        self.assertEqual(self.client.get('/').status_code,401)
        self.assertEqual(self.client.get('/health').status_code,200)
        response=self.client.get('/semana',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertIn('Programação semanal'.encode(),response.data)
        self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
    def test_save_days(self):
        self.assertEqual(self.client.post('/semana',json={'dias':[0,2]},headers=self.headers).status_code,200)
        self.assertEqual(weekly.defaults(),[0,2])
        self.assertEqual(self.client.post('/semana',json={'dias':[99]},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/semana',data={'dias':'0'},headers=self.headers).status_code,415)
    def test_choice_token_and_closed_window(self):
        clock=datetime(2026,10,4,12,tzinfo=weekly.TZ)
        week=date(2026,10,5)
        with patch('weekly.now',return_value=clock):
            url='/escolher/'+weekly.token(week)
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(self.client.post(url,data={'dias':['1','4']}).status_code,200)
            self.assertEqual(weekly.claim(week),['2026-10-06','2026-10-09'])
            self.assertEqual(self.client.post(url,data={'dias':['0']}).status_code,400)
            self.assertEqual(self.client.get(url+'x').status_code,400)
    def test_manual_dates_validation(self):
        self.assertEqual(self.client.post('/agendar',headers=self.headers,json={'usuario':'fake','senha':'fake','datas':['not-a-date']}).status_code,400)

if __name__=='__main__':unittest.main()

class LegacyDeploymentTests(unittest.TestCase):
    def test_unconfigured_deploy_preserves_manual_without_saved_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'ADMIN_PASSWORD':'','DATA_DIR':folder,'RU_USER':'saved-user','RU_PASSWORD':'saved-password'}):
            client=app.test_client()
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get('/semana').status_code,200)
            self.assertIn('Vamos configurar'.encode(),client.get('/semana').data)
            self.assertEqual(client.post('/semana',json={'dias':[0]}).status_code,503)
            response=client.post('/agendar',json={'datas':['2099-10-05']})
            self.assertEqual(response.status_code,400)
            self.assertNotIn(b'saved-password',response.data)
            self.assertNotIn(b'saved-user',client.get('/').data)

class FreeSetupTests(unittest.TestCase):
    def test_protected_panel_refuses_transient_settings(self):
        with patch.dict(os.environ, {'ADMIN_PASSWORD':'long-admin-password','AUTOMATION_ENABLED':'false','STATE_BACKEND':''}):
            c=app.test_client()
            headers={'Authorization':'Basic '+base64.b64encode(b'admin:long-admin-password').decode()}
            self.assertEqual(c.get('/semana').status_code,401)
            self.assertIn('persistência'.encode(),c.get('/semana',headers=headers).data)
            self.assertEqual(c.post('/semana',json={'dias':[0]},headers=headers).status_code,503)

    def test_public_choice_refuses_transient_state(self):
        with patch.dict(os.environ, {'APP_SECRET':'x'*40,'AUTOMATION_ENABLED':'false','STATE_BACKEND':''}), patch('weekly.now',return_value=datetime(2026,10,4,14,tzinfo=weekly.TZ)), patch('weekly.choose') as choose:
            c=app.test_client()
            url='/escolher/'+weekly.token(date(2026,10,5))
            self.assertEqual(c.get(url).status_code,503)
            self.assertEqual(c.post(url,data={'dias':['0']}).status_code,503)
            choose.assert_not_called()
