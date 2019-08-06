# -*- coding: utf-8 -*-

import configparser
import psycopg2
from psycopg2.extensions import AsIs
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
        'admin': {'token': config.get('admin', 'token')},
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
def cursor(db_name=None):
    conn = psycopg2.connect(
        host=config['db']['host'],
        port=config['db']['port'],
        database=db_name or config['db']['name'],
        user=config['db']['user'],
    )
    conn.set_session(autocommit=True)
    yield conn.cursor()
    conn.close()

def get_spare_prefix(project_name):
    return '%s_spare_' % project_name

def get_template_name(project_name):
    return '%s_template' % project_name

def get_spare(cr, project_name):
    spare_prefix = get_spare_prefix(project_name)
    prefix = '%s%%' % spare_prefix
    cr.execute('''
        SELECT datname from  pg_database where
        datname like %s ORDER BY datname
    ''', (prefix,))
    return [x[0] for x in cr.fetchall()]

def exist(cr, db_name):
    cr.execute('''
        SELECT datname from  pg_database where
        datname = %s ORDER BY datname
    ''', (db_name,))
    result = cr.fetchall()
    return bool(result)


def spare_create(cr, project_name):
    spare_name = get_next_spare_name(cr, project_name)
    user = config['projects'][project_name]['user']
    template = '%s_template' % project_name
    cr.execute(
        'CREATE DATABASE "%s" WITH OWNER "%s" TEMPLATE "%s";', (
        AsIs(spare_name),
        AsIs(user),
        AsIs(template),
    ))
    return spare_name


def get_next_spare_name(cr, project_name):
    spares = get_spare(cr, project_name)
    spare_number = 1
    if spares:
        spare_number = int(spares[-1].split('_')[-1]) + 1
    spare_prefix = get_spare_prefix(project_name)
    return '%s%02i' % (spare_prefix, spare_number)


def setup_db():
    db_name = config['db']['name']
    with cursor('postgres') as cr:
        if not exist(cr, db_name):
            cr.execute('CREATE DATABASE "%s" WITH OWNER "%s";', (
                AsIs(db_name), AsIs(config['db']['user'])
            ))
    with cursor(db_name) as cr:
        cr.execute("""
            CREATE TABLE IF NOT EXISTS port_mapping (
                id serial NOT NULL PRIMARY KEY,
                project VARCHAR(255),
                date TIMESTAMP NOT NULL,
                merge_id INTEGER NOT NULL,
                port INTEGER NOT NULL
            )""")
