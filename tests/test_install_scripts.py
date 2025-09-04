import os
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_sh_creates_venv_and_desktop(tmp_path):
    # copy required files to temp working directory
    work = tmp_path / 'work'
    work.mkdir()
    for fname in ['install.sh', 'requirements.txt', 'tv.py']:
        shutil.copy(ROOT / fname, work / fname)

    home = tmp_path / 'home'
    desktop = home / 'Desktop'
    desktop.mkdir(parents=True)

    env = os.environ.copy()
    env['HOME'] = str(home)
    env['SKIP_PIP'] = '1'

    # run installer with blank answers to prompts
    subprocess.run(['bash', 'install.sh'], cwd=work, env=env, input='\n\n', text=True, check=True)

    assert (work / 'venv').exists()
    assert (work / 'Channels').exists()
    assert (desktop / 'TVPlayer.desktop').exists()


def test_install_ps1_contains_venv_and_shortcut():
    content = (ROOT / 'install.ps1').read_text()
    assert 'python -m venv' in content
    assert 'CreateShortcut' in content
