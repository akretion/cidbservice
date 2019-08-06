# -*- coding: utf-8 -*-
import psycopg2


def get_cursor(
    app, database, db_host=None, db_user=None, db_port=None, autocommit=True
):
    conn = psycopg2.connect(
        host=db_host or app.config["db_host"],
        port=db_port or app.config["db_port"],
        database=database,
        user=db_user or app.config["db_user"],
    )
    conn.set_session(autocommit=autocommit)
    return conn.cursor(), conn
