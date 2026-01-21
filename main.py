#!/usr/bin/env python3
"""Main entry point for anime-dl system.

Modes:
- grabber: Run the episode grabber
- api: Run the MyJDownloader API server
- watch: Run the file watcher and mover
- web: Run the web interface

Usage: python main.py <mode> [options]
"""

import argparse
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, '.venv', 'bin', 'python')
VENV_GUNICORN = os.path.join(BASE_DIR, '.venv', 'bin', 'gunicorn')
VENV_STREAMLIT = os.path.join(BASE_DIR, '.venv', 'bin', 'streamlit')

def main():
    parser = argparse.ArgumentParser(description="Anime DL Main Script")
    parser.add_argument('mode', choices=['grabber', 'api', 'watch', 'web'], help="Mode to run")
    parser.add_argument('--host', default='127.0.0.1', help="Host for API/Web server")
    parser.add_argument('--port', type=int, default=5000, help="Port for API/Web server")
    args = parser.parse_args()

    if args.mode == 'grabber':
        cmd = [VENV_PYTHON, '-u', os.path.join(BASE_DIR, 'app', 'grabber.py')]
        subprocess.run(cmd)
    elif args.mode == 'api':
        cmd = [
            VENV_GUNICORN,
            '--workers', '2',
            '--max-requests', '300',
            '--max-requests-jitter', '50',
            '--bind', f'{args.host}:{args.port}',
            'app.api:app'
        ]
        subprocess.run(cmd, cwd=BASE_DIR)
    elif args.mode == 'watch':
        cmd = [
            VENV_PYTHON, '-u', os.path.join(BASE_DIR, 'app', 'anime-dl.py'),
            '--config', os.path.join(BASE_DIR, 'config', 'config.yaml')
        ]
        subprocess.run(cmd)
    elif args.mode == 'web':
        cmd = [
            VENV_STREAMLIT, 'run', 'web.py',
            '--server.port', str(args.port),
            '--server.address', args.host
        ]
        subprocess.run(cmd, cwd=BASE_DIR)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()