"""Supervisiona web e worker, preservando modo manual antes da ativação."""
import logging
import os
import signal
import subprocess
import sys
import time
import weekly

logging.basicConfig(level=logging.INFO)
processes = []
def stop(*_):
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    raise SystemExit(1)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def validate_automation():
    weekly.secret()
    if len(os.environ.get('ADMIN_PASSWORD', '')) < 16:
        raise ValueError('Configure ADMIN_PASSWORD com pelo menos 16 caracteres.')
    if not os.environ.get('RU_USER') or not os.environ.get('RU_PASSWORD'):
        raise ValueError('Configure RU_USER e RU_PASSWORD.')
    if not weekly.hour('REMINDER_TIME','09:00') < weekly.hour('BOOK_TIME','15:00') < weekly.hour('CUTOFF_TIME','15:55') < __import__('datetime').time(16):
        raise ValueError('Horários devem obedecer: aviso < reserva < limite < 16:00.')

if __name__ == '__main__':
    enabled = os.environ.get('AUTOMATION_ENABLED', 'false').lower() == 'true'
    if enabled:
        try:
            validate_automation()
        except (RuntimeError, ValueError) as exc:
            enabled = False
            logging.error('Automação desativada: %s', exc)
    else:
        logging.info('Modo manual. Configure o servidor e AUTOMATION_ENABLED=true para ativar a rotina semanal.')
    try:
        processes.append(subprocess.Popen([sys.executable, '-m', 'gunicorn', '--workers', '1', '--threads', '4', '--timeout', '1800', '--bind', '0.0.0.0:' + os.environ.get('PORT', '10000'), 'app:app']))
        if enabled:
            processes.append(subprocess.Popen([sys.executable, 'worker.py']))
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    finally:
        stop()
