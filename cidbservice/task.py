# -*- coding: utf-8 -*-

from celery import Celery
from psycopg2.extensions import AsIs


celery = Celery(
    'cidbservice',
    broker=config.get('celery', 'broker')
)

@celery.task
def spare_pool_task(project_name, params):

    spare_pool = params['spare_pool']
    db_template = params['db_template']
    db_host = params['db_host']
    db_port = params['db_port']
    db_user = params['db_user']
    spare_prefix = params['spare_prefix']
    template_prefix = params['template_prefix']
    user = params['user']
    try:
        conn = None

        def spare_count(cr):
            prefix = '%s%%' % spare_prefix
            cr.execute('''
                SELECT count(*) from  pg_database where
                datname like %s
            ''', (prefix,))
            res = cr.fetchall()
            return res[0][0]

        while True:
            cr, conn = get_cursor(
                db_template,
                db_host=db_host,
                db_port=db_port,
                db_user=db_user,
            )
            count = spare_count(cr)
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
                    user,
                    template_prefix,
                )
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


@celery.task
def refresh_task(project_name, params):
    try:
        conn = None
        template_prefix = params['spare_prefix']
        prefix = '%s_%%' % (
            template_prefix,
        )

        cr, conn = get_cursor(
            params['db_template'],
            db_host=params['db_host'],
            db_port=params['db_port'],
            db_user=params['db_user'],
        )
        cr.execute('''
            SELECT datname FROM pg_database
            WHERE datname like %s
        ''', (prefix,))
        res = cr.fetchall()
        for r in res:
            datname = r[0]
            app.logger.info('drop spare database "%s"' % datname)
            cr.execute('DROP DATABASE IF EXISTS "%s"', (AsIs(datname),))

        spare_pool_task.delay(project_name, params)

    except:
        app.logger.error('error deleting spare databases "%s" project' % (
            project_name
        ))
    finally:
        if conn:
            conn.close()


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


