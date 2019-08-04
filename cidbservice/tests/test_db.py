# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from ..tools import cursor
from ..task import spare_pool_task
from .common import CommonCase


class TestDbService(CommonCase):

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

    def test_db_refresh_without_spare(self):
        self.create_db('foo_template', 'foo', 'version_a')
        self.assertEqual(
            self.client.get("db/refresh/foo").status_code, 200)
        self.check_db_version('foo_spare_01', 'version_a')
        self.check_db_version('foo_spare_02', 'version_a')
        self.check_db_version('foo_spare_03', 'version_a')

    def test_db_refresh_with_spare(self):
        self.create_db('foo_template', 'foo', 'version_a')
        self.client.get("db/refresh/foo")

        self.create_db('foo_template', 'foo', 'version_b')
        self.assertEqual(
            self.client.get("db/refresh/foo").status_code, 200)
        self.check_db_version('foo_spare_01', 'version_b')
        self.check_db_version('foo_spare_02', 'version_b')
        self.check_db_version('foo_spare_03', 'version_b')

    def test_get_db_with_spare(self):
        self.create_db('foo_template', 'foo', 'version_a')
        self.client.get("db/refresh/foo")

        self.assertEqual(
            self.client.get("db/get/foo/foo_1234").status_code, 200)
        self.check_db_version('foo_1234', 'version_a')

        # Ensure that a new spare have been created
        self.check_db_version('foo_spare_01', 'version_a')
        self.check_db_version('foo_spare_02', 'version_a')
        self.check_db_version('foo_spare_03', 'version_a')

    def test_get_db_without_spare(self):
        self.create_db('foo_template', 'foo', 'version_a')

        self.assertEqual(
            self.client.get("db/get/foo/foo_1234").status_code, 200)
        self.check_db_version('foo_1234', 'version_a')

        # Ensure that a new spare have been created
        self.check_db_version('foo_spare_01', 'version_a')
        self.check_db_version('foo_spare_02', 'version_a')
        self.check_db_version('foo_spare_03', 'version_a')

    def test_get_db_with_wrong_name(self):
        self.create_db('foo_template', 'foo', 'version_a')
        response = self.client.get("db/get/foo/bar_1234")
        self.assertEqual(response.status_code, 400)
        self.assertIn('Wrong db name', response.data)
