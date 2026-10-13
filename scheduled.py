"""Entrada de execução única para o runner gratuito do GitHub."""
import logging
import os
import sys
import time
import weekly
import github_state
import worker


def wait_for_booking():
    """Um runner iniciado antes das 09h aguarda sem reservar antecipadamente."""
    clock = weekly.now()
    if clock.weekday() != 6:
        return
    booking = weekly.deadline(weekly.monday(clock.date()))
    if clock < booking:
        print('Runner preparado: aguardando domingo às 09:00 (Brasília).', flush=True)
    while clock < booking:
        time.sleep(min(30, (booking - clock).total_seconds()))
        clock = weekly.now()


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if os.environ.get('SCHEDULE_ENABLED', '').lower() != 'true':
        print('Programação inativa: cadastre os Secrets e SCHEDULE_ENABLED=true.')
        return 1
    try:
        weekly.secret()
        if not github_state.configured() or not os.environ.get('STATE_TOKEN'):
            raise RuntimeError('Configure o estado cifrado no GitHub.')
        if not os.environ.get('RU_USER') or not os.environ.get('RU_PASSWORD'):
            raise RuntimeError('Cadastre RU_USER e RU_PASSWORD nos Secrets do GitHub.')
        weekly.validate_schedule()
        if os.environ.get('CHECK_ONLY', '').lower() == 'true':
            days = weekly.defaults()
            print(f'Configuração e persistência verificadas: {len(days)} dias predefinidos; reservas domingo às 09:00 (Brasília). Nenhum WhatsApp ou reserva enviado.')
        else:
            if os.environ.get('WAIT_FOR_BOOKING', '').lower() == 'true':
                wait_for_booking()
            result = worker.tick()
            print('Resultado da rotina semanal: ' + result, flush=True)
            if result in ('verificar no RU', 'executando', 'prazo encerrado', 'sem credenciais', 'ocupado'):
                return 1
        return 0
    except Exception as exc:
        # Não imprimir a exceção: falhas externas podem conter credenciais.
        logging.error('Falha na programação. Confira configuração, disponibilidade do GitHub e histórico do painel. Nenhuma repetição automática de reserva já iniciada.')
        return 1

if __name__ == '__main__':
    sys.exit(main())
