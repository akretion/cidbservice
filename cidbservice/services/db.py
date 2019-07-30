# -*- coding: utf-8 -*-

import requests
from retrying import retry
from psycopg2.extensions import AsIs
from flask import abort


class DbService(object):

    def get_provision_param(self, project, key):

        try:
            return app.config['provision_%s_%s' % (project, key)]
        except:
            app.logger.error(
                "can't find value for the key %s for the project %s" %
                (key, project)
            )
            app.logger.error(app.config.get_namespace('provision_'))

    def get_celery_params(self, app, project):
        return {
            'spare_pool': get_provision_param(project, 'spare_pool'),
            'db_template': app.config['db_template'],
            'db_host': app.config['db_host'],
            'db_port': app.config['db_port'],
            'db_user': app.config['db_user'],
            'ci_ref_db': app.config['db_ci_ref_db'],
            'spare_prefix': get_provision_param(project, 'spare_prefix'),
            'template_user': get_provision_param(project, 'template_user'),
            'template_prefix': get_provision_param(project, 'template_prefix'),
            'user': get_provision_param(project, 'user'),
        }

    def spare_last_number(self, cr, spare_prefix):
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

    def spare_create(self, cr, project_name, spare_prefix=None,
                     template_user=None, template_prefix=None, user=None):

        if not spare_prefix:
            spare_prefix = get_provision_param(project_name, 'spare_prefix')
        if not template_user:
            template_user = get_provision_param(project_name, 'template_user')
        if not template_prefix:
            template_prefix = get_provision_param(project_name, 'template_prefix')
        if not user:
            user = get_provision_param(project_name, 'user')

        spare_number = int(spare_last_number(cr, spare_prefix)) + 1
        spare_db = '%s%02i' % (
            spare_prefix,
            spare_number,
        )
        app.logger.info('create spare database "%s"' % spare_db)
        cr.execute('CREATE DATABASE "%s" WITH OWNER "%s" TEMPLATE "%s";', (
            AsIs(spare_db),
            AsIs(user),
            AsIs(template_prefix + project_name),
        ))

        app.logger.info('%s %s %s %s' % (
            spare_db, user, template_prefix, project_name)
        )
        return spare_number

    def add_db(self):
        """ Webhook for gitlab CI.
        When a PR is created/updated gitlab will call this webhook
        This allow to the service to store information related to this PR
        and create rename a customer database"""
        db_name = None
        merge_request = request.get_json()
        g.merge_request = merge_request
        attributes = merge_request['object_attributes']
        state = attributes['state']
        for label in merge_request.get('labels', []):
            if label['title'].lower() == app.config['service_ci_label'] \
                    and state == 'opened':
                project_name = merge_request['project']['name']
                project_id = merge_request['project']['id']
                merge_id = attributes['iid']
                merge_commit = attributes['last_commit']['id']
                source_branch = attributes['source_branch']
                test_url = '%s-%s' % (
                    source_branch,
                    get_provision_param(project_name, 'test_url_suffix')
                )

                db_name = '%i_%s' % (merge_id, merge_commit)

                cr, conn = get_cursor(app.config['db_ci_ref_db'])
                cr.execute('''
                    INSERT INTO merge_request(
                        merge_id, merge_commit, merge_request,
                        merge_date, merge_test_url, project
                    )
                    VALUES(%s, %s, %s, now(), %s, %s);
                ''', (
                    merge_id,
                    merge_commit,
                    json.dumps(merge_request),
                    test_url,
                    project_name
                ))
                try:
                    conn = None
                    cr, conn = get_cursor(app.config['db_template'])

                    # avoid duplicate
                    cr.execute('''
                        SELECT count(*) FROM pg_database
                        WHERE datname = %s
                    ''', (db_name,))
                    res = cr.fetchone()
                    if not res[0]:
                        cr.execute('''
                            DROP DATABASE IF EXISTS "%s";
                        ''', (AsIs(db_name),))

                        spare_prefix = get_provision_param(
                            project_name, 'spare_prefix'
                        )
                        last_number = spare_last_number(cr, spare_prefix)
                        if last_number:
                            spare_number = int(last_number)
                        else:
                            spare_number = int(spare_create(cr, project_name))

                        db_spare = '%s%02i' % (
                            spare_prefix,
                            spare_number,
                        )
                        cr.execute('''
                            ALTER DATABASE "%s" RENAME TO "%s"
                        ''', (AsIs(db_spare), AsIs(db_name)))

                        params = get_celery_params(app, project_name)
                        spare_pool_task.delay(project_name, params)

                    # trigger gitlab-runner
                    trigger_url = '%s/api/v4/projects/%s/trigger/pipeline' % (
                        app.config['runner_trigger_url'],
                        project_id,
                    )
                    data = {
                        'token': app.config['runner_token'],
                        'ref': source_branch,
                    }
                    requests.post(trigger_url, data=data)

                except Exception:
                    abort(500)
                finally:
                    if conn:
                        conn.close()
                break

        if not db_name:
            abort(404)

        return db_name

    def refresh_db(self, project_name):
        app.logger.info('triggering refeshing spare databases "%s" project: ' % (
            project_name,
        ))
        app.logger.info(repr(app.config))
        app.logger.info(repr(project_name))
        params = get_celery_params(app, project_name)
        return '%s\n' % str(refresh_task.delay(project_name, params))

    def drop_db(self, project_name, db_name):
        app.logger.info('triggering drop database "%s"' % db_name)
        params = get_celery_params(app, project_name)
        return '%s\n' % str(drop_task.delay(db_name, params))

    @retry(stop_max_delay=60*60*1000, wait_fixed=500)
    def wait_db(self, db_name):
        res = None
        try:
            conn = None
            cr, conn = get_cursor(app.config['db_template'])
            cr.execute('''
                SELECT count(*) FROM pg_database
                where datname = %s
            ''', (db_name,))
            res = cr.fetchall()
            if res[0][0]:
                return db_name
            else:
                raise Exception('KO')
        finally:
            if conn:
                conn.close()

    def create_demo_db(db, project):
        try:
            conn = None
            cr, conn = get_cursor(app.config['db_template'])
            cr.execute('DROP DATABASE IF EXISTS "%s";', (AsIs(db),))
            cr.execute('CREATE DATABASE "%s" WITH OWNER "%s";', (
                AsIs(db), AsIs(get_provision_param(project, 'user'))
            ))
        except psycopg2.ProgrammingError:
            app.logger.info(
                'Impossible to create "%s" (maybe already exists)' % db
            )
        finally:
            if conn:
                conn.close()

    def get_db(self, commit):
        result = None
        try:
            message = '''
                not a PR to test (not a "%s" labeled PR or not
                triggered from a PR event)...
            ''' % app.config['service_ci_label']
            invalid_pr = 'INVALID_PR="%s"' % message

            conn = None
            cr, conn = get_cursor(app.config['db_ci_ref_db'])
            cr.execute('''
                SELECT merge_id, merge_commit, merge_test_url, project
                FROM merge_request WHERE merge_commit=%s
            ''', (commit,))
            rows = cr.fetchall()
            if not rows:
                return invalid_pr

            db = '%i_%s' % (rows[0][0], rows[0][1])
            db_test = '%s_test' % db
            test_url = rows[0][2]
            project = rows[0][3]

            wait_db(db)
            create_demo_db(db_test, project)
            result = ['DB_NAME=' + db, 'DB_TEST_NAME=' + db_test]

            db_host = get_provision_param(project, 'host')
            if db_host:
                result.append(
                    'DB_HOST=' + db_host
                )

            provision_port = get_provision_param(project, 'port')
            if provision_port:
                result.append(
                    'DB_PORT=' + provision_port
                )

            provision_user = get_provision_param(project, 'user')
            if provision_user:
                result.append(
                    'DB_USER=' + provision_user
                )

            provision_password = get_provision_param(project, 'password')
            if provision_password:
                result.append(
                    'DB_PASSWORD=' + provision_password
                )
            # test env
            result.append('VIRTUAL_HOST=' + test_url)

            return ' '.join(result)
        except Exception:
            return invalid_pr
        finally:
            if conn:
                conn.close()

        return invalid_pr
