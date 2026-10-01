"""Estado persistente e agenda semanal de uma única conta."""
import base64
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Sao_Paulo')

def now():
    return datetime.now(TZ)

def hour(name, default):
    return time.fromisoformat(os.environ.get(name, default))

def monday(today):
    return today + timedelta(days=7 - today.weekday())

def deadline(week):
    return datetime.combine(week - timedelta(days=1), hour('BOOK_TIME', '15:00'), TZ)

def secret():
    value = os.environ.get('APP_SECRET', '')
    if len(value) < 32:
        raise RuntimeError('Configure APP_SECRET com pelo menos 32 caracteres.')
    return value.encode()

def token(week):
    payload = week.isoformat()
    digest = hmac.new(secret(), payload.encode(), hashlib.sha256).digest()
    return payload + '.' + base64.urlsafe_b64encode(digest).decode().rstrip('=')

def token_week(value, clock=None):
    from datetime import date
    try:
        payload, _ = value.split('.', 1)
        week = date.fromisoformat(payload)
        clock = clock or now()
        if not hmac.compare_digest(value, token(week)) or week.weekday() != 0:
            raise ValueError()
        if clock >= deadline(week) or clock < deadline(week) - timedelta(days=7):
            raise ValueError()
        return week
    except (ValueError, TypeError):
        raise ValueError('Link inválido ou encerrado. A escolha fecha no domingo, no horário da execução.')

@contextmanager
def db():
    import github_state
    remote = github_state.configured()
    snapshot, sha = github_state.read() if remote else (None, None)
    if remote:
        conn = sqlite3.connect(':memory:')
        if snapshot is not None:
            conn.deserialize(snapshot)
    else:
        folder = Path(os.environ.get('DATA_DIR', './data'))
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        conn = sqlite3.connect(folder / 'weekly.sqlite', timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, days TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS weeks (week TEXT PRIMARY KEY, days TEXT, reminder TEXT, status TEXT, results TEXT)')
        conn.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)', (json.dumps([0,1,2,3,4]),))
        conn.commit()
        yield conn
        conn.commit()
        if remote:
            updated = conn.serialize()
            if updated != snapshot:
                github_state.write(updated, sha)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def validate_days(days):
    if not isinstance(days, list) or any(type(d) is not int or d not in range(5) for d in days):
        raise ValueError('Selecione apenas dias úteis válidos.')
    return sorted(set(days))

def defaults():
    with db() as c:
        return json.loads(c.execute('SELECT days FROM settings WHERE id=1').fetchone()[0])

def set_defaults(days):
    days = validate_days(days)
    with db() as c:
        c.execute('UPDATE settings SET days=? WHERE id=1', (json.dumps(days),))

def state(week):
    with db() as c:
        c.execute('INSERT OR IGNORE INTO weeks(week) VALUES (?)', (week.isoformat(),))
        return dict(c.execute('SELECT * FROM weeks WHERE week=?', (week.isoformat(),)).fetchone())

def choose(week, days, clock=None):
    days = validate_days(days)
    clock = clock or now()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR IGNORE INTO weeks(week) VALUES (?)', (week.isoformat(),))
        row = c.execute('SELECT status FROM weeks WHERE week=?', (week.isoformat(),)).fetchone()
        if clock >= deadline(week) or row['status']:
            raise ValueError('A execução desta semana já foi iniciada ou o prazo encerrou.')
        c.execute('UPDATE weeks SET days=? WHERE week=?', (json.dumps(days), week.isoformat()))

def claim(week):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR IGNORE INTO weeks(week) VALUES (?)', (week.isoformat(),))
        row = c.execute('SELECT * FROM weeks WHERE week=?', (week.isoformat(),)).fetchone()
        if row['status']:
            return None
        days = json.loads(row['days']) if row['days'] is not None else json.loads(c.execute('SELECT days FROM settings WHERE id=1').fetchone()[0])
        c.execute("UPDATE weeks SET status='executando', days=? WHERE week=?", (json.dumps(days), week.isoformat()))
        return [(week + timedelta(days=d)).isoformat() for d in days]

def finish(week, results):
    status = 'concluído' if all(x['status'] == 'ok' for x in results) else 'verificar no RU'
    with db() as c:
        c.execute('UPDATE weeks SET status=?, results=? WHERE week=?', (status, json.dumps(results, ensure_ascii=False), week.isoformat()))

def reminder_update(week, status):
    with db() as c:
        c.execute('UPDATE weeks SET reminder=? WHERE week=?', (status, week.isoformat()))

class ExecutionBusy(RuntimeError):
    pass

@contextmanager
def execution_lock():
    """Lock compartilhado entre o worker e o servidor web (Linux)."""
    import fcntl
    folder = Path(os.environ.get('DATA_DIR', './data'))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (folder / 'execution.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ExecutionBusy('Já existe um agendamento em execução.')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def send_reminder(week):
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    if os.environ.get('WHATSAPP_PROVIDER', 'callmebot') == 'callmebot':
        return send_callmebot(week)
    required = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM', 'WHATSAPP_TO', 'TWILIO_CONTENT_SID', 'PUBLIC_URL']
    if any(not os.environ.get(k) for k in required):
        raise RuntimeError('Configure as variáveis de WhatsApp e PUBLIC_URL.')
    url = os.environ['PUBLIC_URL'].rstrip('/') + '/escolher/' + token(week)
    if not url.startswith('https://'):
        raise RuntimeError('PUBLIC_URL precisa usar HTTPS.')
    sid = os.environ['TWILIO_ACCOUNT_SID']
    if not (sid.startswith('AC') and sid.isalnum()):
        raise RuntimeError('TWILIO_ACCOUNT_SID inválido.')
    values = {'From': os.environ['TWILIO_WHATSAPP_FROM'], 'To': os.environ['WHATSAPP_TO'],
              'ContentSid': os.environ['TWILIO_CONTENT_SID'],
              'ContentVariables': json.dumps({'1': week.strftime('%d/%m/%Y'), '2': url})}
    auth = base64.b64encode((sid + ':' + os.environ['TWILIO_AUTH_TOKEN']).encode()).decode()
    req = Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
                  data=urlencode(values).encode(), headers={'Authorization': 'Basic ' + auth})
    with urlopen(req, timeout=20) as response:
        data = json.load(response)
    if not data.get('sid'):
        raise RuntimeError('O provedor não retornou identificação da mensagem.')
    return 'aceito pelo provedor: ' + data['sid']


def history():
    with db() as c:
        return [dict(row) for row in c.execute('SELECT * FROM weeks ORDER BY week DESC LIMIT 12')]


def send_callmebot(week):
    """API gratuita para o próprio número, após autorização no WhatsApp."""
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    import re
    phone = os.environ.get('CALLMEBOT_PHONE', '')
    key = os.environ.get('CALLMEBOT_APIKEY', '')
    public = os.environ.get('PUBLIC_URL', '').rstrip('/')
    if not re.fullmatch(r'\+?[0-9]{10,15}', phone) or not key or not public.startswith('https://'):
        raise RuntimeError('Configure CALLMEBOT_PHONE, CALLMEBOT_APIKEY e PUBLIC_URL.')
    text = ('RU: escolha os dias da semana de ' + week.strftime('%d/%m/%Y') + '. '
            'A escolha fecha domingo às ' + hour('BOOK_TIME', '15:00').strftime('%H:%M') +
            ' (Brasília). Sem resposta, usaremos os dias predefinidos. ' + public + '/escolher/' + token(week))
    query = urlencode({'phone': phone, 'apikey': key, 'text': text})
    try:
        with urlopen(Request('https://api.callmebot.com/whatsapp.php?' + query), timeout=25) as response:
            result = response.read(20_000).decode('utf-8', errors='replace')
        if 'message queued' not in result.lower() and 'message sent' not in result.lower():
            raise RuntimeError()
    except Exception:
        # A URL inclui a chave; nunca registrar a exceção original.
        raise RuntimeError('O WhatsApp não confirmou o envio. Verifique sua ativação no CallMeBot.') from None
    return 'aceito pelo CallMeBot; confira a entrega no WhatsApp'
