# -*- coding: utf-8 -*-
# Copyright 2019 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import pytest
from ..tools import get_cursor
from ..task import spare_pool_task

@pytest.mark.usefixtures('client_class')
class TestSuite:

    def create_db(self, db_name, owner, version):
        with get_cursor() as cr:
            cr.execute("DROP DATABASE IF EXISTS {}".format(db_name))
            cr.execute(
                "CREATE DATABASE {} OWNER {}".format(
                    db_name, owner
                ))
        with get_cursor(db_name) as cr:
            cr.execute("CREATE TABLE {} (name char)".format(version))

    def check_db_version(self, name, version):
        with get_cursor(name) as cr:
            cr.execute("""SELECT EXISTS
                (SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'schema_name'
                    AND table_name = %s
                )""" , version)
            res = cr.fetchall()
            import pdb; pdb.set_trace()

    def test_db_refresh(self):
        self.create_db('foo_template', 'foo', 'version_a')
        spare_pool_task('foo')
        import pdb; pdb.set_trace()
