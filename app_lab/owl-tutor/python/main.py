"""Owl Tutor App Lab app: the Teach web page (port 8000) + the owl's eyes on the LED matrix.

install.sh copies the copilot, the Teach server, the eyes helper, config.env and the data next to this file.
The page calls /api/eyes and the server switches the eyes through the Bridge (owl_eyes/python/eyes_bridge.py).
The model servers (8081, 8082) run as systemd services outside the app.
"""
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from arduino.app_utils import App  # noqa: E402


def serve():
    sys.argv = ["teach", "--host", "0.0.0.0", "--port", "8000"]
    from teach import server  # imported here so the Bridge is ready first
    server.main()


threading.Thread(target=serve, daemon=True).start()
App.run()
