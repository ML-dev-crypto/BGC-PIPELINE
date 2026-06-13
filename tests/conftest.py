import subprocess
import time
import pytest


@pytest.fixture(scope='session', autouse=True)
def start_backend():
    """Start the Flask backend server before tests and shut it down after."""
    proc = subprocess.Popen(['python', 'backend/backend_api.py'])
    time.sleep(3)  # wait for startup
    yield
    proc.terminate()
