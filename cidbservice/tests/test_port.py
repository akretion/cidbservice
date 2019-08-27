# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>

from ..tools import cursor
from .common import CommonCase


class TestPortService(CommonCase):
    def setUp(self):
        super().setUp()
        self.headers = {"X-Gitlab-Token": "foo-token"}
        with cursor() as cr:
            cr.execute("DELETE FROM port_mapping")

    def get_port(self, project_name, db_name):
        with cursor() as cr:
            cr.execute(
                """SELECT port
                FROM port_mapping
                WHERE project=%s AND db_name=%s""",
                (project_name, db_name),
            )
            res = cr.fetchall()
            if res:
                return res[0][0]
            else:
                return None

    def _test_getting_port(self, project, db_name, expected_port):
        response = self.get("port/lock/{}/{}".format(project, db_name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response.data), expected_port)
        port = self.get_port(project, db_name)
        self.assertEqual(port, expected_port)

    def test_lock_port(self):
        self._test_getting_port("foo", "foo_42", 8000)

    def test_relock_port(self):
        self._test_getting_port("foo", "foo_42", 8000)
        self._test_getting_port("foo", "foo_42", 8000)

    def test_lock_all_port(self):
        for i in range(0, 5):
            self._test_getting_port("foo", "foo_4{}".format(i), 8000 + i)
        self.assertEqual(self.get("port/lock/foo/foo_45").status_code, 404)

    def test_release_port(self):
        self._test_getting_port("foo", "foo_42", 8000)
        self.assertEqual(self.get("port/release/foo/foo_42").status_code, 200)
        self.assertIsNone(self.get_port("foo", "foo_42"))

    def test_redirect_port(self):
        self.get("port/lock/foo/foo_42")
        self.headers = {}
        response = self.get("port/redirect/foo/foo_42")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "https://ci.dy:8000")

    def test_redirect_missing_port(self):
        response = self.get("port/redirect/foo/foo_42")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"No port reserved for the database", response.data)

    def test_wrong_token(self):
        self.headers = {"X-Gitlab-Token": "fake"}
        self.assertEqual(self.get("port/lock/foo/foo_42").status_code, 401)
        self.assertEqual(self.get("port/release/foo/foo_42").status_code, 401)

    def test_wrong_token_project(self):
        self.assertEqual(self.get("port/lock/bar/bar_42").status_code, 401)
        self.assertEqual(self.get("port/release/bar/bar_42").status_code, 401)

    def test_admin_token(self):
        self.headers = {"X-Gitlab-Token": "super-token"}
        self.assertEqual(self.get("port/lock/foo/foo_42").status_code, 200)
        self.assertEqual(self.get("port/release/foo/foo_42").status_code, 200)

    def test_with_wrong_name(self):
        for path in ["lock", "release", "redirect"]:
            response = self.get("port/{}/foo/bar_1234".format(path))
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"Wrong db name", response.data)

    def test_port_not_active(self):
        self.headers = {"X-Gitlab-Token": "bar-token"}
        self.assertEqual(self.get("port/lock/bar/bar_42").status_code, 401)
