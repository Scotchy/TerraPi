import base64
import hashlib
import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from monitoring.server import DashboardLogin, HISTORY, HistoryServer
from monitoring.store import Store


class HistoryHTTPTests(unittest.TestCase):
    def test_history_remains_authenticated_and_readable_while_collector_disconnected(self):
        def encode(value):
            return base64.b64encode(value).decode()
        salt = os.urandom(12)
        digest = hashlib.pbkdf2_hmac("sha512", b"example", salt, 101)
        login = DashboardLogin("dashboard", f"$7$101${encode(salt)}${encode(digest)}")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "history.sqlite3"))
            recorder = SimpleNamespace(subscribed=threading.Event())
            with HistoryServer(("127.0.0.1", 0), store, login, recorder) as server:
                worker = threading.Thread(target=server.serve_forever)
                worker.start()
                addr = "http://127.0.0.1:" + str(server.server_port)
                def request(path, password):
                    auth = "Basic " + encode(("dashboard:" + password).encode())
                    with urlopen(Request(addr + path, headers={"Authorization": auth}), timeout=3) as response:
                        return json.load(response)
                try:
                    path = HISTORY + "?start=60&end=180&points=2"
                    for url, password, code in [(path, "incorrect", 401), ("/health", "", 503),
                                                (HISTORY + "?start=2&end=1", "example", 400)]:
                        with self.assertRaises(HTTPError) as error:
                            request(url, password)
                        self.assertEqual(error.exception.code, code)
                    self.assertEqual(request(path, "example")["summary"]["unknown"], 2)
                    recorder.subscribed.set()
                    self.assertTrue(request("/health", "")["connected"])
                finally:
                    server.shutdown()
                    worker.join()
