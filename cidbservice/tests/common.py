# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>


import unittest
from ..app import app
from ..task import celery
from ..tools import cursor


class CommonCase(unittest.TestCase):

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
        super(CommonCase, self).setUp()
        celery.conf.task_always_eager = True
        self.clear()
        self.client = app.test_client()
