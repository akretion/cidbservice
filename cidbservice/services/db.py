# -*- coding: utf-8 -*-

from psycopg2.extensions import AsIs

from ..task import refresh_task, spare_pool_task
from ..tools import cursor, get_spare, spare_create


class DbService(object):
    def __init__(self, logger, config):
        super(DbService, self).__init__()
        self.config = config
        self.logger = logger

    def refresh(self, project_name):
        self.logger.info(
            "triggering refeshing spare databases '%s' project: "
            % (project_name,)
        )
        return "%s\n" % str(refresh_task.delay(project_name))

    def get(self, project_name, db_name):
        with cursor() as cr:
            spares = get_spare(cr, project_name)
            if spares:
                spare = spares[-1]
            else:
                spare = spare_create(cr, project_name)
            cr.execute(
                """ALTER DATABASE "%s" RENAME TO "%s" """,
                (AsIs(spare), AsIs(db_name)),
            )

        # Create consummed spare in background
        spare_pool_task.delay(project_name)
        return "OK"
