import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from robot import app


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        for name, value in {
            "robot": None, "ROBOT_IP": "172.20.10.4", "armed": False,
            "busy": False, "last_error": "", "action_lock": asyncio.Lock(),
        }.items():
            replacement = patch.object(app, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.conn = SimpleNamespace(
            connect=AsyncMock(), disconnect=AsyncMock(),
            pc=SimpleNamespace(connectionState="connected"),
            datachannel=SimpleNamespace(
                data_channel_opened=True,
                pub_sub=SimpleNamespace(
                    channel=SimpleNamespace(readyState="open"),
                    publish_without_callback=Mock(),
                ),
            ),
        )
        factory = patch.object(app, "Go2Connection", return_value=self.conn)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        after = patch.object(app, "after_connect", new_callable=AsyncMock)
        after.start()
        self.addCleanup(after.stop)
        self.client = TestClient(app.app, base_url="http://127.0.0.1", client=("127.0.0.1", 45000))
        self.addCleanup(self.client.close)
        self.headers = {"X-Control-Token": app.TOKEN}

    def test_new_ip_is_used_and_reported_without_arming(self):
        response = self.client.post(
            "/api/connect", json={"ip": "10.254.159.2"}, headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.factory.call_args.kwargs["ip"], "10.254.159.2")
        status = self.client.get("/api/status", headers=self.headers).json()
        self.assertEqual(status["ip"], "10.254.159.2")
        self.assertTrue(status["connected"])
        self.assertFalse(status["armed"])
        self.assertIn('value="10.254.159.2"', self.client.get("/").text)

    def test_missing_body_keeps_startup_address(self):
        response = self.client.post("/api/connect", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.factory.call_args.kwargs["ip"], "172.20.10.4")

    def test_invalid_ip_does_not_touch_current_connection(self):
        app.robot = self.conn
        for ip in ["999.1.1.1", "http://10.254.159.2", "", "::1"]:
            with self.subTest(ip=ip):
                response = self.client.post(
                    "/api/connect", json={"ip": ip}, headers=self.headers,
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(app.ROBOT_IP, "172.20.10.4")
                self.conn.disconnect.assert_not_awaited()
                self.factory.assert_not_called()

    def test_timeout_reports_attempted_ip_and_releases_connection(self):
        self.conn.connect.side_effect = TimeoutError()
        response = self.client.post(
            "/api/connect", json={"ip": "10.254.159.2"}, headers=self.headers,
        )
        self.assertEqual(response.status_code, 502)
        self.assertIn("10.254.159.2", response.json()["detail"])
        self.assertIn("TimeoutError", response.json()["detail"])
        self.conn.disconnect.assert_awaited_once()
        self.assertIsNone(app.robot)
        self.assertFalse(app.busy)
        self.assertFalse(app.armed)
        self.assertFalse(app.action_lock.locked())

    def test_connection_still_requires_session_token(self):
        response = self.client.post("/api/connect", json={"ip": "10.254.159.2"})
        self.assertEqual(response.status_code, 403)
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
