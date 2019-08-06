# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>

from ..tools import cursor, exist
from ..task import spare_pool_task, celery
from .common import CommonCase


class TestDbService(CommonCase):

    def setUp(self):
        super().setUp()
        self.create_db('foo_template', 'foo', 'version_a')
        self.headers = {'X-Gitlab-Token': 'foo-token'}

    def create_db(self, db_name, owner, version):
        with cursor() as cr:
            cr.execute("DROP DATABASE IF EXISTS {}".format(db_name))
            cr.execute(
                "CREATE DATABASE {} OWNER {}".format(
                    db_name, owner
                ))
        with cursor(db_name) as cr:
            cr.execute("CREATE TABLE {} (name char)".format(version))

    def check_db_version(self, name, version):
        with cursor(name) as cr:
            cr.execute("""SELECT EXISTS
                (SELECT 1
                FROM information_schema.tables
                WHERE table_name = %s
                )""" , (version,))
            res = cr.fetchall()
            self.assertTrue(res[0][0])

    def check_foo_spare_ready(self, version):
        self.check_db_version('foo_spare_01', version)
        self.check_db_version('foo_spare_02', version)
        self.check_db_version('foo_spare_03', version)

    def test_db_refresh_without_spare(self):
        self.assertEqual(self.get("db/refresh/foo").status_code, 200)
        self.check_foo_spare_ready('version_a')

    def test_db_refresh_with_spare(self):
        self.client.get("db/refresh/foo")

        self.create_db('foo_template', 'foo', 'version_b')
        self.assertEqual(self.get("db/refresh/foo").status_code, 200)
        self.check_foo_spare_ready('version_b')

    def test_get_db_with_spare_no_eager(self):
        celery.conf.task_always_eager = False
        self.create_db('foo_spare_1', 'foo', 'version_a')
        self.create_db('foo_spare_2', 'foo', 'version_a')
        self.assertEqual(self.get("db/get/foo/foo_1234").status_code, 200)
        self.check_db_version('foo_1234', 'version_a')
        with cursor() as cr:
            self.assertTrue(exist(cr, 'foo_spare_1'))
            self.assertFalse(exist(cr, 'foo_spare_2'))
            self.assertFalse(exist(cr, 'foo_spare_3'))

    def test_get_db_without_spare_no_eager(self):
        celery.conf.task_always_eager = False
        self.assertEqual(self.get("db/get/foo/foo_1234").status_code, 200)
        self.check_db_version('foo_1234', 'version_a')
        with cursor() as cr:
            self.assertFalse(exist(cr, 'foo_spare_1'))
            self.assertFalse(exist(cr, 'foo_spare_2'))
            self.assertFalse(exist(cr, 'foo_spare_3'))

    def test_get_db_refresh_pool(self):
        self.assertEqual(self.get("db/get/foo/foo_1234").status_code, 200)
        self.check_foo_spare_ready('version_a')

    def test_get_db_with_wrong_name(self):
        response = self.get("db/get/foo/bar_1234")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Wrong db name', response.data)

    def test_wrong_token(self):
        self.headers = {'X-Gitlab-Token': 'fake'}
        self.assertEqual(self.get("db/get/foo/foo_1234").status_code, 401)
        self.assertEqual(self.get("db/refresh/foo").status_code, 401)

    def test_wrong_project_token(self):
        self.assertEqual(self.get("db/get/bar/bar_1234").status_code, 401)
        self.assertEqual(self.get("db/refresh/bar").status_code, 401)

    def test_admin_token(self):
        self.headers = {'X-Gitlab-Token': 'super-token'}
        self.assertEqual(self.get("db/get/foo/foo_1234").status_code, 200)
        self.assertEqual(self.get("db/refresh/foo").status_code, 200)
