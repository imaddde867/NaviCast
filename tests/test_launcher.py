import os
import subprocess
from pathlib import Path


def test_launcher_reports_missing_configuration(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith('NAVICAST_')}
    env['NAVICAST_ENV_FILE'] = str(tmp_path / 'absent.env')
    result = subprocess.run(['bash', 'start_navicast.sh'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'NAVICAST_DB_PASSWORD' in result.stderr


def test_launcher_validates_port(tmp_path):
    env = dict(os.environ, PORT='not-a-port', NAVICAST_ENV_FILE=str(tmp_path / 'absent.env'))
    result = subprocess.run(['bash', 'start_navicast.sh'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'PORT' in result.stderr
