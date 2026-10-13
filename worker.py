"""Processo separado, sempre ativo; nunca inicia a partir de uma visita à página."""
import logging
import os
import time
from datetime import datetime
import weekly

log = logging.getLogger('worker')

def tick(clock=None, runner=None, sender=None):
    clock = clock or weekly.now()
    if clock.weekday() != 6:
        return 'fora do domingo'
    week = weekly.monday(clock.date())
    row = weekly.state(week)
    booking = weekly.deadline(week)
    reminder = datetime.combine(clock.date(), weekly.hour('REMINDER_TIME', '08:00'), weekly.TZ)
    if weekly.reminders_enabled() and reminder <= clock < booking and not row['reminder']:
        # Gravado antes do envio: resposta ambígua não causa mensagens duplicadas.
        weekly.reminder_update(week, 'enviando; se interrompido, verificar no provedor')
        try:
            result = (sender or weekly.send_reminder)(week)
            weekly.reminder_update(week, result)
        except Exception:
            weekly.reminder_update(week, 'falha; verificar configuração/entrega no provedor')
            log.error('Aviso não enviado. As reservas continuam programadas.')
    cutoff = datetime.combine(clock.date(), weekly.hour('CUTOFF_TIME', '15:55'), weekly.TZ)
    if row['status']:
        return 'já processada' if row['status'] == 'concluído' else row['status']
    if clock < booking:
        return 'antes das 09h'
    if clock >= cutoff:
        return 'prazo encerrado'
    if not os.environ.get('RU_USER') or not os.environ.get('RU_PASSWORD'):
        log.error('Configure RU_USER e RU_PASSWORD; nenhuma reserva realizada.')
        return 'sem credenciais'
    try:
        with weekly.execution_lock():
            dates = weekly.claim(week)
            if dates is None:
                return 'já processada'
            if not dates:
                weekly.finish(week, [])
                return 'concluído'
            if runner is None:
                from app import executar_agendamentos
                runner = executar_agendamentos
            try:
                results = runner(os.environ['RU_USER'], os.environ['RU_PASSWORD'], dates, deadline=cutoff)
            except Exception:
                results = [{'data': d, 'status': 'erro', 'mensagem': 'Execução interrompida. Confira o RU antes de repetir.'} for d in dates]
            weekly.finish(week, results)
            log.info('Semana %s processada. Consulte o painel.', week)
            return 'concluído' if all(x['status'] == 'ok' for x in results) else 'verificar no RU'
    except weekly.ExecutionBusy:
        log.info('Outra execução está ativa; aguardando o próximo ciclo.')
        return 'ocupado'

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    weekly.secret()
    # Um único worker por volume. O lock é liberado automaticamente ao encerrar.
    import fcntl
    from pathlib import Path
    folder = Path(os.environ.get('DATA_DIR', './data'))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (folder / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                tick()
            except Exception:
                log.error('Falha no ciclo do worker; verificar configuração e volume persistente.')
            time.sleep(30)
