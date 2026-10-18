"""Disparo externo da rotina semanal, sempre para a semana atual."""
import json
from pathlib import Path
import scheduled
import weekly


def main(request_path=None):
    try:
        clock = weekly.now()
        if clock.weekday() != 6:
            raise ValueError('A solicitação só pode executar no domingo.')
        path = Path(request_path) if request_path else Path(__file__).parent / '.github' / 'ru-request.json'
        request = json.loads(path.read_text(encoding='utf-8'))
        expected = weekly.monday(clock.date()).isoformat()
        if not isinstance(request, dict) or request.get('target_week') != expected:
            raise ValueError('Solicitação de outra semana; nenhuma reserva iniciada.')
    except (ValueError, TypeError, OSError):
        print('Solicitação recusada: confira o domingo e a semana do arquivo .github/ru-request.json.')
        return 1
    print('Executando solicitação para a semana de ' + expected, flush=True)
    return scheduled.main()


if __name__ == '__main__':
    raise SystemExit(main())
