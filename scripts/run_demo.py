"""Start the local AI parser and WhatsApp worker alongside an existing ngrok server.

Run from any directory: python scripts/run_demo.py
Requires backend/.env on the machine hosting the WhatsApp server.
Use --check to verify configuration without starting processes.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        import requests
        from dotenv import dotenv_values
        from backend.integrations.twilio.config import Settings
    except ImportError:
        print('Install dependencies first: python -m pip install -r backend/requirements.txt -r backend/requirements-whatsapp.txt')
        return 1
    env_path = ROOT / 'backend/.env'
    if not env_path.exists():
        print('Missing backend/.env. Run this on the WhatsApp server machine, where Eva configured Twilio and Supabase.')
        return 1
    env = {**os.environ, **{key: value for key, value in dotenv_values(env_path).items() if value is not None}}
    env.update({'AI_BASE_URL': 'http://127.0.0.1:8002',
                'GOOGLE_EXECUTION_URL': 'https://timeslice-google-api.vercel.app',
                'DASHBOARD_URL': 'https://timeslice-dashboard.vercel.app'})
    required = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'TWILIO_ACCOUNT_SID',
                'TWILIO_AUTH_TOKEN', 'TWILIO_WEBHOOK_URL', 'AI_SERVICE_TOKEN', 'GEMINI_API_KEY']
    missing = [key for key in required if not env.get(key, '').strip()]
    if missing:
        print('Set these in backend/.env (values stay private): ' + ', '.join(missing))
        return 1
    try:
        Settings(**{key.lower(): value for key, value in env.items()})
    except Exception:
        print('Backend settings are invalid. Check HTTPS URLs and nonempty required credentials in backend/.env.')
        return 1
    try:
        # Empty plan cannot schedule anything. 422 proves the shared token passed
        # authentication and the request then failed body validation as expected.
        response = requests.post(env['GOOGLE_EXECUTION_URL'] + '/api/execute', json={},
            headers={'Authorization': 'Bearer ' + env['AI_SERVICE_TOKEN']}, timeout=20, allow_redirects=False)
    except requests.RequestException:
        print('Google API could not be reached. Check internet access and the production deployment.')
        return 1
    if response.status_code != 422:
        print('Shared execution token check failed (HTTP ' + str(response.status_code) + '). Match AI_SERVICE_TOKEN on this worker and the Google API Vercel project, then redeploy that API.')
        return 1
    print('Shared Google execution token: verified. No events or tasks were created.', flush=True)
    print('Keep the existing WhatsApp web server and ngrok running.', flush=True)
    if args.check:
        print('Configuration checks passed. Live Gemini/Twilio message delivery still needs the demo test.')
        return 0
    children = []

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        try:
            response = requests.get(env['AI_BASE_URL'] + '/health', timeout=2)
            reusable = response.ok and response.json().get('service') == 'TimeSlice AI Agent' and response.json().get('gemini_configured')
        except (requests.RequestException, ValueError):
            reusable = False
        if not reusable:
            children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app',
                '--host', '127.0.0.1', '--port', '8002', '--no-access-log'], cwd=ROOT, env=env))
            for _ in range(60):
                if children[0].poll() is not None:
                    print('AI service exited. Check port 8002 and installed dependencies.')
                    return 1
                try:
                    if requests.get(env['AI_BASE_URL'] + '/health', timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            else:
                print('AI service did not become ready.')
                return 1
        children.append(subprocess.Popen([sys.executable, '-m', 'backend.jobs.worker'], cwd=ROOT, env=env))
        print('AI parser and WhatsApp worker are running. Keep this terminal open; Ctrl+C stops processes started here.', flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                print('A demo process exited; stopping its companion. Check the error above.')
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nStopping demo processes…')
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
