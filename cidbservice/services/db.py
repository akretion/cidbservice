# -*- coding: utf-8 -*-

import requests
from retrying import retry
from psycopg2.extensions import AsIs
from flask import abort
from ..task import refresh_task, spare_pool_task
from ..tools import cursor, get_spare, spare_create, spare_create


class DbService(object):

    def __init__(self, logger, config):
        super(DbService, self).__init__()
        self.config = config
        self.logger = logger

    def get_provision_param(self, project, key):

        try:
            return app.config['provision_%s_%s' % (project, key)]
        except:
            app.logger.error(
                "can't find value for the key %s for the project %s" %
                (key, project)
            )
            app.logger.error(app.config.get_namespace('provision_'))

    def refresh(self, project_name):
        self.logger.info(
            "triggering refeshing spare databases '%s' project: " % (
            project_name,
        ))
        return '%s\n' % str(refresh_task.delay(project_name))

    def get(self, project_name, db_name):
        if not db_name.startswith(project_name):
            return abort(400, 'Wrong db name')
        with cursor() as cr:
            spares = get_spare(cr, project_name)
            if spares:
                spare = spares[-1]
            else:
                spare = spare_create(cr, project_name)
            cr.execute(
                """ALTER DATABASE "%s" RENAME TO "%s" """,
                (AsIs(spare), AsIs(db_name)))

        # Create consummed spare in background
        spare_pool_task.delay(project_name)
        return "OK"
