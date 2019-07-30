# -*- coding: utf-8 -*-

import configparser
import psycopg2
from psycopg2.extensions import AsIs
from .helper import get_cursor


def parse(app, config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    # service
    app.config['service_token'] = config.get('service', 'token')
    app.config['service_ci_label'] = config.get('service', 'ci_label').lower()
    # runner
    app.config['runner_token'] = config.get('runner', 'token')
    app.config['runner_trigger_url'] = config.get('runner', 'trigger_url')
    # db
    app.config['db_host'] = config.get('db', 'host')
    app.config['db_template'] = config.get('db', 'template')
    app.config['db_user'] = config.get('db', 'user')
    app.config['db_port'] = config.get('db', 'port')
    app.config['db_ci_ref_db'] = config.get('db', 'ci_ref_db')

    # provision
    projects = ['']
    try:
        projects.extend([
            p.strip() for p in config.get('provision', 'projects').split(',')
        ])
    except ValueError:
        pass

    def get_section(project):
        section = 'provision'
        if project:
            section += '_%s' % project
        return section

    def get_key(section, key):
        key = '%s_%s' % (
            section,
            key
        )
        return key

    for project in projects:
        section = get_section(project)
        provision_str_key = [
            'template_prefix',
            'template_user',
            'spare_prefix',
            'host',
            'port',
            'user',
            'password',
            'spare_prefix',
            'template_user',
            'test_backend_prefix',
            'test_url_suffix',
            'template_prefix',
        ]
        for key in provision_str_key:
            val = config.get('provision', key)
            try:
                val = config.get(section, key)
            except configparser.NoOptionError:
                app.logger.warn(
                  'invalid str config param "%s", section "%s"' %
                  (key, section)
                )
            app.logger.error("config %s = %s" % (get_key(section, key), val))
            app.config[get_key(section, key)] = val

        provision_int_key = [
            'spare_pool',
            'max_test_backend',
            'test_backend_base_port',
        ]
        for key in provision_int_key:
            val = config.getint('provision', key)
            app.logger.error('key "%s" "%s" "%s"' % ('provision', key, val))
            try:
                val = config.getint(section, key)
            except:
                app.logger.warn(
                  'invalid int config param "%s", section "%s"' %
                  (key, section)
                )
            app.logger.error("config %s = %s" % (get_key(section, key), val))
            app.config[get_key(section, key)] = val

    app.config['init_done'] = True

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


