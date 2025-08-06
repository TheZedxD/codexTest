import subprocess, sys

FILES = ['TVPlayer_Complete copy.py', 'qr_code_dialog.py']

def test_python_files_compile():
    for f in FILES:
        subprocess.check_call([sys.executable, '-m', 'py_compile', f])
