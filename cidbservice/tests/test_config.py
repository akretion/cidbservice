# -*- coding: utf-8 -*-

import unittest
from ..tools import parse, setup_db, cursor


class InitialisationCase(unittest.TestCase):

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
            'admin': {
                'token': u'super-token',
                },
            'projects': {
                u'bar': {
                    'domain': u'ci.dy',
                    'port_mapping_active': False,
                    'port_mapping_max': None,
                    'port_mapping_start': None,
                    'spare_pool': 2,
                    'token': u'bar-token',
                    'user': u'foo',
                    },
                u'foo': {
                    'domain': u'ci.dy',
                    'port_mapping_active': True,
                    'port_mapping_max': 5,
                    'port_mapping_start': 8000,
                    'spare_pool': 3,
                    'token': u'foo-token',
                    'user': u'foo',
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
