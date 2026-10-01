"""Estado cifrado e compartilhado entre Render gratuito e GitHub Actions."""
import base64
import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from cryptography.fernet import Fernet, InvalidToken


def configured():
    return os.environ.get('STATE_BACKEND') == 'github'


def cipher():
    import weekly
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(weekly.secret()).digest()))


def api(method='GET', data=None):
    repo = os.environ.get('STATE_REPOSITORY', '')
    token = os.environ.get('STATE_TOKEN', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not token:
        raise RuntimeError('Configure STATE_REPOSITORY e STATE_TOKEN para salvar os dias.')
    url = 'https://api.github.com/repos/' + repo + '/contents/runtime/state.enc'
    if method == 'GET':
        url += '?ref=main'
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'agendador-ru'}
    req = Request(url, method=method, headers=headers,
                  data=json.dumps(data).encode() if data is not None else None)
    try:
        with urlopen(req, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404 and method == 'GET':
            # A ausência do arquivo só é inicializável se o repositório é acessível.
            probe = Request('https://api.github.com/repos/' + repo, headers=headers)
            try:
                with urlopen(probe, timeout=25):
                    return None
            except (HTTPError, URLError):
                raise RuntimeError('Repositório de estado indisponível. Verifique o token.') from None
        if exc.code in (409, 422):
            raise RuntimeError('Os dias foram alterados em outra sessão. Atualize a página e tente novamente.') from None
        raise RuntimeError('Não foi possível salvar ou ler os dias no GitHub. Verifique o token.') from None
    except (URLError, TimeoutError):
        raise RuntimeError('GitHub temporariamente indisponível. Tente novamente.') from None


def read():
    encryption = cipher()
    row = api()
    if row is None:
        return None, None
    try:
        payload = base64.b64decode(row['content'])
        if len(payload) > 900_000:
            raise ValueError()
        return encryption.decrypt(payload), row['sha']
    except (InvalidToken, KeyError, ValueError):
        raise RuntimeError('Não foi possível abrir os dados. APP_SECRET deve ser igual no Render e no GitHub.') from None


def write(snapshot, sha):
    data = {'message': 'Atualiza estado cifrado do RU [skip ci]', 'branch': 'main',
            'content': base64.b64encode(cipher().encrypt(snapshot)).decode()}
    if sha:
        data['sha'] = sha
    api('PUT', data)
