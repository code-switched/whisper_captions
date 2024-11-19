import subprocess
import time
import os

def launch_processes():
    # Get the path to the Python interpreter in the virtual environment
    venv_python = os.path.join(os.getcwd(), "venv", "Scripts", "python.exe")

    server_cmd = [venv_python, "whisper_online_server.py"]
    client_cmd = [venv_python, "client_connect.py"]

    client_process = subprocess.Popen(['start', 'cmd', '/k', 'title Captions CLIENT && '] + client_cmd, shell=True)
    time.sleep(1)
    server_process = subprocess.Popen(['start', 'cmd', '/k', 'title Captions SERVER && '] + server_cmd, shell=True)

if __name__ == "__main__":
    launch_processes()