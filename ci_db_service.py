# /usr/bin/env python2

import configparser
import json

from flask import Flask, request, g, abort
from celery import Celery
from psycopg2.extensions import AsIs
import psycopg2


CONFIG_FILE = '/etc/ci_db_service.conf'
PATH_ADD_DB = '/add_db'
PATH_GET_DB = '/get_db/<commit>'


app = Flask(__name__)
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

celery = Celery(
    'ci_db_service',
    broker=config.get('celery', 'broker'),
)


def get_cursor(database, db_host=None, db_user=None, autocommit=True):
    conn = psycopg2.connect(
        host=db_host or app.config['db_host'],
        database=database,
        user=db_user or app.config['db_user'],
    )
    conn.set_session(autocommit=autocommit)
    return conn.cursor(), conn


def setup_service():

    db = app.config['db_ci_ref_db']
    try:
        conn = None
        cr, conn = get_cursor(app.config['db_template'])
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
                merge_request json NOT NULL
            );
        ''')
    except:
        app.logger.critical(
            'Impossible to create "merge_request" table'
        )
        raise
    finally:
        if conn:
            conn.close()


@app.before_first_request
def init():

    # service
    app.config['service_token'] = config.get('service', 'token')
    app.config['service_ci_label'] = config.get('service', 'ci_label')
    # db
    app.config['db_host'] = config.get('db', 'host')
    app.config['db_template'] = config.get('db', 'template')
    app.config['db_user'] = config.get('db', 'user')
    app.config['db_ci_ref_db'] = config.get('db', 'ci_ref_db')
    # provision
    app.config['provision_template_prefix'] = \
        config.get('provision', 'template_prefix')
    app.config['provision_template_user'] = \
        config.get('provision', 'template_user')
    app.config['provision_spare_prefix'] = \
        config.get('provision', 'spare_prefix')
    app.config['provision_spare_pool'] = \
        config.getint('provision', 'spare_pool')
    app.config['provision_host'] = \
        config.get('provision', 'host')
    app.config['provision_port'] = \
        config.get('provision', 'port')
    app.config['provision_user'] = \
        config.get('provision', 'user')
    app.config['provision_password'] = \
        config.get('provision', 'password')
    app.config['provision_spare_prefix'] = \
        config.get('provision', 'spare_prefix')
    app.config['provision_template_user'] = \
        config.get('provision', 'template_user')
    app.config['template_prefix'] = \
        config.get('provision', 'template_prefix')

    setup_service()


@app.before_request
def before_request():
    token = app.config['service_token']
    if not token or request.headers.get('X-Gitlab-Token') != token:
        abort(403)


def spare_last_number(cr, project_name):
    spare_last_number = 0
    prefix = 'spare_%s_%%' % project_name
    cr.execute('''
         SELECT max(datname) FROM pg_database where
         datname like %s
    ''', (prefix, ))
    res = cr.fetchall()
    if res[0][0]:
        _, _, spare_last_number = res[0][0].split('_')
    return spare_last_number


def spare_create(cr, project_name, spare_prefix=None,
                 template_user=None, template_prefix=None):

    if not spare_prefix:
        spare_prefix = app.config['provision_spare_prefix']
    if not template_user:
        template_user = app.config['provision_template_user']
    if not template_prefix:
        template_prefix = app.config['provision_template_prefix']

    spare_number = int(spare_last_number(cr, project_name)) + 1
    spare_db = '%s%s_%i' % (
        spare_prefix,
        project_name,
        spare_number,
    )
    app.logger.info('create spare database "%s"' % spare_db)
    cr.execute('CREATE DATABASE "%s" WITH OWNER "%s" TEMPLATE "%s";', (
        AsIs(spare_db),
        AsIs(template_user),
        AsIs(template_prefix + project_name),
    ))
    return spare_number


@celery.task
def spare_pool_task(merge_request, params):

    spare_pool = params['spare_pool']
    db_template = params['db_template']
    db_host = params['db_host']
    db_user = params['db_user']
    spare_prefix = params['spare_prefix']
    template_user = params['template_user']
    template_prefix = params['template_prefix']

    try:
        project_name = merge_request['project']['name']
        conn = None

        def spare_count(cr, project_name):
            prefix = 'spare_%s%%' % project_name
            app.logger.info(prefix)
            cr.execute('''
                SELECT count(*) from  pg_database where
                datname like %s
            ''', (prefix,))
            res = cr.fetchall()
            return res[0][0]

        while True:
            cr, conn = get_cursor(db_template, db_host, db_user)
            count = spare_count(cr, project_name)
            if count >= spare_pool:
                app.logger.info('spare pool ok for %s (%i/%i)' % (
                    project_name, count, spare_pool
                ))
                break
            else:
                spare_create(
                    cr,
                    project_name,
                    spare_prefix,
                    template_user,
                    template_prefix,
                )
    except Exception:
        raise
    finally:
        if conn:
            conn.close()


@app.route(PATH_ADD_DB, methods=['POST'])
def add_db():
    db_name = ''
    merge_request = request.get_json()
    g.merge_request = merge_request
    for label in merge_request['labels']:
        if label['title'] == app.config['service_ci_label']:

            project_name = merge_request['project']['name']
            attributes = merge_request['object_attributes']
            merge_id = attributes['id']
            merge_commit = attributes['last_commit']['id']
            db_name = '%i_%s' % (merge_id, merge_commit)

            try:
                conn = None
                cr, conn = get_cursor(app.config['db_template'])

                # avoid duplicate
                cr.execute('''
                    SELECT count(*) FROM pg_database
                    WHERE datname = %s
                ''', (db_name,))
                res = cr.fetchall()
                if res[0][0]:
                    conn.close()
                    return db_name

                cr.execute('''
                    DROP DATABASE IF EXISTS "%s";
                ''', (AsIs(db_name),))

                last_number = spare_last_number(cr, project_name)
                if last_number:
                    spare_number = int(last_number)
                else:
                    spare_number = int(spare_create(cr, project_name))

                db_spare = '%s_%i' % (
                    app.config['provision_spare_prefix'] + project_name,
                    spare_number,
                )
                cr.execute('''
                    ALTER DATABASE "%s" RENAME TO "%s"
                ''', (AsIs(db_spare), AsIs(db_name)))

                conn.close()
                cr, conn = get_cursor(app.config['db_ci_ref_db'])
                cr.execute('''
                    INSERT INTO merge_request(
                        merge_id, merge_commit, merge_request
                    )
                    VALUES(%s, %s, %s);
                ''', (
                    merge_id,
                    merge_commit,
                    json.dumps(merge_request)
                ))
                params = {
                    'spare_pool': app.config['provision_spare_pool'],
                    'db_template': app.config['db_template'],
                    'db_host': app.config['db_host'],
                    'db_user': app.config['db_user'],
                    'spare_prefix': app.config['provision_spare_prefix'],
                    'template_user': app.config['provision_template_user'],
                    'template_prefix': app.config['provision_template_prefix'],
                }
                spare_pool_task.delay(merge_request, params)
            except Exception:
                abort(500)
            finally:
                if conn:
                    conn.close()
            break

    return db_name


@app.route(PATH_GET_DB, methods=['GET'])
def get_db(commit):
    result = None
    try:
        conn = None
        cr, conn = get_cursor(app.config['db_ci_ref_db'])
        cr.execute('''
            SELECT merge_id, merge_commit
            FROM merge_request WHERE merge_commit=%s
        ''', (commit,))
        rows = cr.fetchall()
        if not rows:
            abort(404)
        db = '%i_%s' % (rows[0][0], rows[0][1])
        result = ' '.join(
            app.config['provision_host'],
            app.config['provision_port'],
            app.config['provision_user'],
            app.config['provision_password'],
            db
        )
        return result
    except Exception:
        raise
        abort(503)
    finally:
        if conn:
            conn.close()
