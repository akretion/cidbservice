# -*- coding: utf-8 -*-

import unittest
from ..tools import parse, setup_db, cursor, CONFIG_FILE


class InitialisationCase(unittest.TestCase):

    def test_config(self):
        config = parse(CONFIG_FILE)
        expected = {
            'celery': {
                'broker': 'amqp://rabbitmq'
                },
            'db': {
                 'host': '',
                 'name': 'ci_ref',
                 'port': '',
                 'user': 'odoo',
                 },
            'admin': {
                'token': 'super-token',
                },
            'projects': {
                'bar': {
                    'domain': 'ci.dy',
                    'port_mapping_active': False,
                    'port_mapping_max': None,
                    'port_mapping_start': None,
                    'spare_pool': 2,
                    'token': 'bar-token',
                    'user': 'foo',
                    },
                'foo': {
                    'domain': 'ci.dy',
                    'port_mapping_active': True,
                    'port_mapping_max': 5,
                    'port_mapping_start': 8000,
                    'spare_pool': 3,
                    'token': 'foo-token',
                    'user': 'foo',
                }}}
        self.assertEqual(config, expected)

    def test_setup(self):
        with cursor('postgres') as cr:
            cr.execute("DROP DATABASE IF EXISTS ci_ref")
        setup_db()
        with cursor('ci_ref') as cr:
            cr.execute("""SELECT EXISTS
                (SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'port_mapping'
                )""" )
            res = cr.fetchall()
            self.assertTrue(res[0][0])
