# -*- coding: utf-8 -*-

import unittest
from ..tools import parse


class ConfigCase(unittest.TestCase):

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


