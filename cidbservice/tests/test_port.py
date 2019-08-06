# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>

from ..tools import cursor
from .common import CommonCase


class TestPortService(CommonCase):

    def setUp(self):
        super(TestPortService, self).setUp()
        self.headers = {'X-Gitlab-Token': 'foo-token'}
        with cursor() as cr:
            cr.execute("DELETE FROM port_mapping")

    def get_port(self, project_name, merge_id):
        with cursor() as cr:
            cr.execute("""SELECT port
                FROM port_mapping
                WHERE project=%s AND merge_id=%s""",
                (project_name, merge_id))
            res = cr.fetchall()
            if res:
                return res[0][0]
            else:
                return None

    def _test_getting_port(self, project, merge_id, expected_port):
        response = self.get("port/lock/{}/{}".format(project, merge_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, str(expected_port))
        port = self.get_port(project, merge_id)
        self.assertEqual(port, expected_port)

    def test_lock_port(self):
        self._test_getting_port('foo', 42, 8000)

    def test_lock_all_port(self):
        for i in range(0, 5):
            self._test_getting_port('foo', 40 + i , 8000 + i)
        self.assertEqual(self.get("port/lock/foo/45").status_code, 404)

    def test_release_port(self):
        self._test_getting_port('foo', 42, 8000)
        self.assertEqual(self.get("port/release/foo/42").status_code, 200)
        self.assertIsNone(self.get_port("foo", 42))

    def test_redirect_port(self):
        self.get("port/lock/foo/42")
        self.headers = {}
        response = self.get('port/redirect/foo/42')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://ci.dy:8000')

    def test_wrong_token(self):
        self.headers = {'X-Gitlab-Token': 'fake'}
        self.assertEqual(self.get("port/lock/foo/42").status_code, 401)
        self.assertEqual(self.get("port/release/foo/42").status_code, 401)

    def test_admin_token(self):
        self.headers = {'X-Gitlab-Token': 'super-token'}
        self.assertEqual(self.get("port/lock/foo/42").status_code, 200)
        self.assertEqual(self.get("port/release/foo/42").status_code, 200)
