# -*- coding: utf-8 -*-
import requests
from psycopg2.extensions import AsIs

from ..task import refresh_task, spare_pool_task
from ..tools import cursor, get_spare, spare_create


class DbService(object):
    def __init__(self, logger, config):
        super(DbService, self).__init__()
        self.config = config
        self.logger = logger

    def refresh(self, project_name, version):
        if version:
            db_name = "{}_{}".format(project_name, version)
        else:
            db_name = project_name
        self.logger.info(
            "triggering refeshing spare databases '%s'" % (db_name)
        )
        return "%s\n" % str(refresh_task.delay(db_name))

    def get(self, project_name, db_name, version):
        if version:
            base_db_name = "{}_{}".format(project_name, version)
        else:
            base_db_name = project_name
        with cursor() as cr:
            spares = get_spare(cr, base_db_name)
            if spares:
                spare = spares[-1]
            else:
                spare = spare_create(cr, project_name, version)
            cr.execute(
                """ALTER DATABASE "%s" RENAME TO "%s" """,
                (AsIs(spare), AsIs(db_name)),
            )

        # Create consummed spare in background
        spare_pool_task.delay(project_name)
        return "OK"

    def clean(self):
        self.logger.info("Start cleaning")
        page = 0
        params = {"state": "opened", "scope": "all", "per_page": 100}
        opened_iid = []
        url = ("{}/api/v4/merge_requests?").format(
            self.config["gitlab"]["host"]
        )
        headers = {"Private-Token": self.config["gitlab"]["token"]}
        while True:
            params["page"] = page
            res = requests.get(url, params=params, headers=headers)
            iid = [x["iid"] for x in res.json()]
            self.logger.info(
                "Request page {} of gitlab found {} MR".format(page, len(iid))
            )
            if iid:
                opened_iid += iid
                page += 1
            else:
                break
        with cursor() as cr:
            cr.execute("SELECT datname FROM pg_database")
            dbs = [x[0] for x in cr.fetchall()]
            for db in dbs:
                iid = None
                try:
                    info = db.split("_")
                    iid = int(info[1])
                except Exception:
                    self.logger.info("Skip clean database {}".format(db))
                    continue
                if iid not in opened_iid:
                    self.logger.info("Drop database {}".format(db))
                    cr.execute("DROP DATABASE {}".format(db))

            cr.execute("SELECT db_name, port FROM port_mapping")
            for db_name, port in cr.fetchall():
                if db_name not in dbs:
                    self.logger.info("Release port {}".format(port))
                    cr.execute(
                        """DELETE FROM port_mapping
                         WHERE db_name=%s""",
                        (db_name),
                    )
        return "ok"
