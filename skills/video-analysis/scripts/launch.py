"""Launch a Colab job stage independently of the notebook connection."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


worker = r'''
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

job, name, encoded = sys.argv[1:]
root = Path(job)
status = root / (name + '.status.json')

def write_status(**fields):
    temporary = status.with_suffix('.pending')
    temporary.write_text(json.dumps({'pid': os.getpid(), **fields}) + '\n')
    temporary.replace(status)

with (root / (name + '.lock')).open('w') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Stage is already running.', flush=True)
        raise SystemExit(1)
    write_status(status='running')
    try:
        result = subprocess.run(json.loads(encoded), cwd=root)
        write_status(status='complete' if result.returncode == 0 else 'failed', exit_code=result.returncode)
    except OSError as error:
        write_status(status='failed', exit_code=1, error=str(error))
        raise
'''


def launch():
    spec = json.loads(os.environ['VIDEO_STAGE_SPEC'])
    job, name, argv = Path(spec['job']), spec['name'], spec['argv']
    if not job.is_absolute() or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        raise ValueError('Supply an absolute job path and a lowercase stage name.')
    if not isinstance(argv, list) or not argv or not all(isinstance(value, str) and value for value in argv):
        raise ValueError('Supply argv as a nonempty list of strings.')
    job.mkdir(parents=True, exist_ok=True)
    with (job / f'{name}.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, '-u', '-c', worker, str(job), name, json.dumps(argv)],
                                   stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
    print(json.dumps({'pid': process.pid, 'job': str(job), 'stage': name}), flush=True)


launch()
