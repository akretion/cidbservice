# /usr/bin/env python2

from flask import abort, redirect

from ..tools import config, cursor


class PortService(object):
    def __init__(self, logger, config):
        super(PortService, self).__init__()
        self.config = config
        self.logger = logger

    def get_existing_port(self, cr, project_name, db_name):
        cr.execute(
            """SELECT port
            FROM port_mapping
            WHERE project=%s
                AND db_name=%s""",
            (project_name, db_name),
        )
        res = cr.fetchall()
        if res:
            return str(res[0][0])
        else:
            return None

    def reserve_port(self, cr, project_name, db_name):
        cr.execute(
            "SELECT port FROM port_mapping WHERE project=%s", (project_name,)
        )
        port_used = [x[0] for x in cr.fetchall()]
        project_config = config["projects"][project_name]
        start_port = project_config["port_mapping_start"]
        stop_port = start_port + project_config["port_mapping_max"]
        for port in range(start_port, stop_port):
            if port not in port_used:
                cr.execute(
                    """INSERT INTO port_mapping(
                        project, date, db_name, port
                    )
                    VALUES(%s, now(), %s, %s);
                """,
                    (project_name, db_name, port),
                )
                return str(port)
        return abort(
            404, "Not more available port please stop existing review apps"
        )

    def lock(self, project_name, db_name):
        with cursor() as cr:
            port = self.get_existing_port(cr, project_name, db_name)
            if port:
                return port
            else:
                return self.reserve_port(cr, project_name, db_name)

    def release(self, project_name, db_name):
        with cursor() as cr:
            cr.execute(
                """DELETE FROM port_mapping
                WHERE project=%s AND db_name=%s""",
                (project_name, db_name),
            )
        return "OK"

    def redirect(self, project_name, db_name):
        with cursor() as cr:
            port = self.get_existing_port(cr, project_name, db_name)
        if port:
            domain = config["projects"][project_name]["domain"]
            return redirect("https://{}:{}".format(domain, port))
        else:
            return abort(404, "No port reserved for the database")
