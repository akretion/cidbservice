# -*- coding: utf-8 -*-

import configparser
import psycopg2
from psycopg2.extensions import AsIs
from .helper import get_cursor
import logging
_logger = logging.getLogger(__name__)
from contextlib import contextmanager


def parse(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    vals = {
        'db': {
            'host': config.get('db', 'host'),
            'user': config.get('db', 'user'),
            'port': config.getint('db', 'port'),
            'name': config.get('db', 'name'),
        },
        'celery': {'broker': config.get('celery', 'broker')},
    }

    # provision
    vals['projects'] = {}
    def get_project_key(key):
        return config.get('project_%s' % project_name, key)

    project_vals = {
        'domain': config.get('provision', 'default_domain'),
        'spare_pool': config.getint('provision', 'default_spare_pool'),
        'port_mapping_active': False,
        'port_mapping_start': None,
        'port_mapping_max': None,
        }

    def update(project, getter, section, key, require=False):
        try:
            project[key] = getattr(config, getter)(section, key)
        except configparser.NoOptionError:
            if require:
                raise Exception(
                    "Missing key '%s' in section %s" %(key, section))
            _logger.info(
                "Section %s no Specific value for %s use default"
                % (section, key))
            pass

    for project_name in config.get('provision', 'projects').split(','):
        project = project_vals.copy()
        vals['projects'][project_name] = project
        project['user'] = project_name

        section = 'provision_%s' % project_name
        update(project, 'get', section, 'user')
        update(project, 'get', section, 'domain')
        update(project, 'getint', section, 'spare_pool')
        update(project, 'getboolean', section, 'port_mapping_active')
        update(project, 'getint', section, 'port_mapping_start')
        update(project, 'getint', section, 'port_mapping_max')
        update(project, 'get', section, 'token', require=True)
    return vals

config = parse('/etc/cidbservice.conf')

@contextmanager
def get_cursor(db_name=None):
    conn = psycopg2.connect(
        host=config['db']['host'],
        port=config['db']['port'],
        database=db_name or config['db']['name'],
        user=config['db']['user'],
    )
    conn.set_session(autocommit=True)
    yield conn.cursor()
    conn.close()

def setup_service(app):
    db = app.config['db_ci_ref_db']
    try:
        conn = None
        cr, conn = get_cursor(app, app.config['db_template'])
        cr.execute('CREATE DATABASE "%s" WITH OWNER "%s";', (
            AsIs(db), AsIs(app.config['db_user'])
        ))
    except psycopg2.ProgrammingError:
        app.logger.info(
            'Impossible to create "%s" (maybe already exists)' % db
        )
    finally:
        if conn:
            conn.close()

    try:
        conn = None
        cr, conn = get_cursor(db)
        cr.execute('''
            CREATE TABLE IF NOT EXISTS merge_request (
                id serial NOT NULL PRIMARY KEY,
                merge_id INTEGER NOT NULL,
                merge_commit VARCHAR(80),
                merge_request json NOT NULL,
                merge_date TIMESTAMP NOT NULL,
                merge_test_url VARCHAR(255),
                backend_name VARCHAR(80),
                project VARCHAR(255)
            );
        ''')
    except:
        app.logger.critical(
            'Impossible to create "merge_request" table'
        )
    finally:
        if conn:
            conn.close()

