import subprocess, sys

FILES = ['tv.py', 'qr_code_dialog.py', 'qr_utils.py']

def test_python_files_compile():
    for f in FILES:
        subprocess.check_call([sys.executable, '-m', 'py_compile', f])
