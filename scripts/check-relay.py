#!/usr/bin/env python3
"""Run trusted tests against candidate Contents; no credentials or real services."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SUITES = ('test_scanner.py', 'test_agent_identity.py', 'test_windows_paths.py',
          'test_stack_identity.py', 'test_negative_airdates.py', 'test_fixture_api.py')
RUNTIME = ('Contents/Code/__init__.py', 'Contents/Scanners/Series/Shoko Relay Scanner.py')
PYTHON2_IMAGE = 'python:2.7.18-slim@sha256:b68d40df862ac07e8955ea0fc0c5454cb4245b6165e79bc8ea2cc69170d9ba62'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--python2', default='docker', help='Python 2.7 executable, or docker')
    args = parser.parse_args()
    trusted = Path(__file__).resolve().parents[1]
    candidate = args.candidate.resolve()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'OPENAI_API_KEY'):
        if env.get(key):
            raise RuntimeError('Do not run candidate code in a credential-holding job')
    with tempfile.TemporaryDirectory(prefix='relay-check-') as tmp:
        fixture = Path(tmp)
        shutil.copytree(candidate / 'Contents', fixture / 'Contents')
        shutil.copytree(trusted / 'tests', fixture / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for suite in SUITES:
            subprocess.run([sys.executable, '-B', '-S', str(fixture / 'tests' / suite)], check=True, env=env)
    grammar = 'import ast; paths = %r; [ast.parse(open(p,"rb").read(),filename=p) for p in paths]; print("Python 2.7 grammar passed")' % (list(RUNTIME),)
    if args.python2 == 'docker':
        subprocess.run(['docker', 'run', '--rm', '--network=none', '--read-only', '--cap-drop=ALL',
                        '--security-opt=no-new-privileges', '--mount',
                        'type=bind,source=%s,target=/src,readonly' % candidate, '-w', '/src',
                        PYTHON2_IMAGE, 'python', '-B', '-c', grammar], check=True, env=env)
    else:
        subprocess.run([args.python2, '-B', '-c', grammar], cwd=candidate, check=True, env=env)


if __name__ == '__main__':
    main()
