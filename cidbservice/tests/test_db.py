# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import pytest
from ..tools import cursor
from ..task import celery, spare_pool_task
from ..app import app
from ..tools import parse
import unittest


class TestApi(unittest.TestCase):

    def clear(self):
        with cursor() as cr:
            cr.execute("""
                 SELECT datname FROM pg_database where
                 datname not in (
                    'postgres',
                    'template1',
                    'template0',
                    'ci_ref')
            """)
            for db in cr.fetchall():
                cr.execute("DROP DATABASE {}".format(db[0]))

    def setUp(self):
        super(TestApi, self).setUp()
        celery.conf.task_always_eager = True
        self.clear()
        self.client = app.test_client()

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

    def test_config(self):
        config = parse('/etc/cidbservice.conf')
        expected = {
            'celery': {
                'broker': u'amqp://rabbitmq'
                },
            'db': {
                 'host': u'db',
                 'name': u'ci_ref',
                 'port': 5432,
                 'user': u'odoo',
                 },
            'projects': {
                u'bar': {
                    'domain': u'ci.dy',
                    'port_mapping_active': False,
                    'port_mapping_max': None,
                    'port_mapping_start': None,
                    'spare_pool': 2,
                    'token': u'456',
                    'user': u'foo',
                    },
                u'foo': {
                    'domain': u'ci.dy',
                    'port_mapping_active': True,
                    'port_mapping_max': 5,
                    'port_mapping_start': 8000,
                    'spare_pool': 3,
                    'token': u'123',
                    'user': u'foo',
                }}}
        self.assertEqual(config, expected)

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
