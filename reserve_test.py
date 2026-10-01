"""Teste real explícito: um único almoço, agora, com credenciais dos Secrets."""
import os
import re
from datetime import date
import weekly
import github_state


def main(runner=None):
    day = os.environ.get('TEST_RESERVATION_DATE', '')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('Informe a data do almoço em AAAA-MM-DD.')
        target = date.fromisoformat(day)
        if target <= weekly.now().date() or target.weekday() >= 5:
            raise ValueError('Escolha um dia útil futuro. O teste é executado agora, mas o almoço precisa ser em uma data futura.')
        weekly.secret()
        if not github_state.configured() or not os.environ.get('STATE_TOKEN'):
            raise ValueError('Configure o armazenamento cifrado no GitHub.')
        if not os.environ.get('RU_USER') or not os.environ.get('RU_PASSWORD'):
            raise ValueError('Cadastre RU_USER e RU_PASSWORD nos Secrets do GitHub.')
        with weekly.execution_lock():
            weekly.claim_reservation_test(day)
            print('Tentando reservar UM almoço para ' + day + ' usando a conta salva. Esta é uma reserva real.', flush=True)
            if runner is None:
                from app import executar_agendamentos
                runner = executar_agendamentos
            try:
                results = runner(os.environ['RU_USER'], os.environ['RU_PASSWORD'], [day])
            except Exception:
                results = [{'data':day,'status':'erro','mensagem':'Teste interrompido. Confira o RU antes de repetir.'}]
            status = weekly.finish_reservation_test(day, results)
            if status == 'concluído':
                print('RESERVA CONFIRMADA PELO RU para ' + day + '. Confira também na sua conta do RU.', flush=True)
                return 0
            print('RESERVA NÃO CONFIRMADA. Confira o RU e o painel antes de repetir. Pode haver indisponibilidade, data ainda não liberada ou mudança da página.', flush=True)
            return 1
    except ValueError as exc:
        print('Teste não iniciado: ' + str(exc), flush=True)
        return 1
    except Exception:
        print('Teste não concluído. Verifique os Secrets, o estado cifrado e o histórico do painel. Confira o RU antes de repetir.', flush=True)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
