"""Entrada de execução única para o runner gratuito do GitHub."""
import logging
import os
import sys
from datetime import time
import weekly
import github_state
import worker


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if os.environ.get('SCHEDULE_ENABLED', '').lower() != 'true':
        print('Programação inativa: cadastre os Secrets e SCHEDULE_ENABLED=true.')
        return 0
    try:
        weekly.secret()
        if not github_state.configured() or not os.environ.get('STATE_TOKEN'):
            raise RuntimeError('Configure o estado cifrado no GitHub.')
        if not os.environ.get('RU_USER') or not os.environ.get('RU_PASSWORD'):
            raise RuntimeError('Cadastre RU_USER e RU_PASSWORD nos Secrets do GitHub.')
        if not weekly.hour('REMINDER_TIME', '09:00') < weekly.hour('BOOK_TIME', '15:00') < weekly.hour('CUTOFF_TIME', '15:55') < time(16):
            raise RuntimeError('Os horários precisam encerrar novas reservas antes das 16h.')
        if os.environ.get('CHECK_ONLY', '').lower() == 'true':
            weekly.defaults()
            print('Configuração e persistência verificadas. Nenhum WhatsApp ou reserva enviado.')
        else:
            worker.tick()
        return 0
    except Exception:
        logging.error('Falha na programação. Confira configuração, disponibilidade do GitHub e histórico do painel. Nenhuma repetição automática de reserva já iniciada.')
        return 1

if __name__ == '__main__':
    sys.exit(main())
