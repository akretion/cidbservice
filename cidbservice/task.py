# -*- coding: utf-8 -*-

from .tools import config, get_cursor
from celery import Celery
from psycopg2.extensions import AsIs
from celery.contrib import rdb
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

celery = Celery(
    'cidbservice',
    broker=config['celery']['broker'])


def get_spare_prefix(project_name):
    return '%s_spare_' % project_name

def get_template_name(project_name):
    return '%s_template' % project_name

def spare_count(cr, project_name):
    spare_prefix = get_spare_prefix(project_name)
    prefix = '%s%%' % spare_prefix
    cr.execute('''
        SELECT count(*) from  pg_database where
        datname like %s
    ''', (prefix,))
    return cr.fetchall()[0][0]

def spare_last_number(cr, spare_prefix):
    spare_last_number = 0
    prefix = '%s_%%' % spare_prefix
    cr.execute('''
         SELECT max(datname) FROM pg_database where
         datname like %s
    ''', (prefix, ))
    res = cr.fetchall()
    if res[0][0]:
        _, _, spare_last_number = res[0][0].split('_')
    return spare_last_number

def spare_create(cr, project_name):
    spare_prefix = get_spare_prefix(project_name)
    spare_number = int(spare_last_number(cr, spare_prefix)) + 1
    spare_db = '%s%02i' % (spare_prefix, spare_number)
    user = config['projects'][project_name]['user']
    template = '%s_template' % project_name
    logger.info('create spare database "%s"' % spare_db)
    cr.execute(
        'CREATE DATABASE "%s" WITH OWNER "%s" TEMPLATE "%s";', (
        AsIs(spare_db),
        AsIs(user),
        AsIs(template),
    ))

    logger.info('DATABASE CREATED name: %s, user: %s, template: %s' % (
        spare_db, user, template)
    )
    return spare_number


@celery.task
def spare_pool_task(project_name):
    with get_cursor() as cr:
        spare_prefix = '%s_spare' % project_name
        spare_pool = config['projects'][project_name]['spare_pool']
        import pdb; pdb.set_trace()
        while True:
            count = spare_count(cr, project_name)
            if count >= spare_pool:
                app.logger.info('spare pool ok for %s (%i/%i)' % (
                    project_name, count, spare_pool
                ))
                break
            else:
                spare_create(cr, project_name)


@celery.task
def refresh_task(project_name):
    with get_cursor() as cr:
        prefix = get_spare_prefix(project_name)
        cr.execute('''
            SELECT datname FROM pg_database
            WHERE datname like %s
        ''', (prefix,))
        res = cr.fetchall()
        try:
            for r in res:
                datname = r[0]
                _logger.info('drop spare database "%s"' % datname)
                cr.execute('DROP DATABASE IF EXISTS "%s"', (AsIs(datname),))
            spare_pool_task.delay(project_name)
        except:
            _logger.error('error deleting spare databases "%s" project' % (
                project_name
            ))


@celery.task
def drop_task(db_name, params):
    try:
        conn = None

        merge_id, merge_commit = db_name.split('_', 1)
        merge_id = int(merge_id)

        if merge_id and merge_commit:
            cr, conn = get_cursor(
                params['ci_ref_db'],
                db_host=params['db_host'],
                db_port=params['db_port'],
                db_user=params['db_user'],
            )
            app.logger.info(
                'delete merge_request merge_id=%i merge_commit=%s' %
                (merge_id, merge_commit)
            )
            cr.execute('''
                DELETE FROM merge_request WHERE
                merge_id=%s AND merge_commit=%s
            ''', (merge_id, merge_commit))

            cr, conn = get_cursor(
                params['db_template'],
                db_host=params['db_host'],
                db_port=params['db_port'],
                db_user=params['db_user'],
            )
            app.logger.info('drop database "%s"' % db_name)
            cr.execute(
                'DROP DATABASE IF EXISTS "%s"',
                (AsIs(db_name),)
            )
    except:
        app.logger.error('error droping database "%s" project' % (
            db_name
        ))
    finally:
        if conn:
            conn.close()


