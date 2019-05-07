# /usr/bin/env python2

import json

import psycopg2
import requests
import configparser
import Queue
from flask import Flask, request, g, abort
from celery import Celery
from psycopg2.extensions import AsIs
from retrying import retry


CONFIG_FILE = '/etc/cidbservice.conf'
PATH_ADD_DB = '/add_db'
PATH_GET_DB = '/get_db/<commit>'
PATH_REFRESH_DB = '/refresh_db/<project_name>'
PATH_DROP_DB = '/drop_db/<db_name>'
PATH_APPS_MAP = '/apps_map/<format_>'
PATH_UPDATE_APPS_MAP = '/update_apps_map/<db_name>'


app = Flask(__name__)
config = configparser.ConfigParser()
config.read(CONFIG_FILE)


class Backend(object):
    def __init__(self, id, domain, backend_name, priority):
        self.id = id
        self.domain = domain
        self.backend_name = backend_name
        self.priority = priority

    def __cmp__(a, b):
        return (a < b) - (a > b)

    def __gt__(self, other):
        return self.priority > other.priority


def get_priority(merge_id, new_merge_id, count, max_priority=1000):
    if merge_id == new_merge_id:
        return max_priority
    else:
        return count


def get_provision_param(project, key):
    return app.config['provision_%s_%s' % (project, key)]

celery = Celery(
    'cidbservice',
    broker=config.get('celery', 'broker'),
)


def get_cursor(database, db_host=None, db_user=None,
               db_port=None, autocommit=True):
    conn = psycopg2.connect(
        host=db_host or app.config['db_host'],
        port=db_port or app.config['db_port'],
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
        raise
    finally:
        if conn:
            conn.close()


@app.before_first_request
def init():

    # service
    app.config['service_token'] = config.get('service', 'token')
    app.config['service_ci_label'] = config.get('service', 'ci_label')
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
		  'invalid str config param "%s", section "%s"' % (
		  key, section)
		)
	    app.config[get_key(section, key)] = val

        provision_int_key = [
            'spare_pool',
            'max_test_backend',
            'test_backend_base_port',
        ]
        for key in provision_int_key:
	    val = config.get('provision', key)
	    try:
		val = config.getint(section, key)
	    except configparser.NoOptionError:
		app.logger.warn(
		  'invalid int config param "%s", section "%s"' % (
		  key, section
		))
	    app.config[get_key(section, key)] = val

    setup_service()


def get_celery_params(app, project):
    return {
        'spare_pool': get_provision_param(project, 'spare_pool'),
        'db_template': app.config['db_template'],
        'db_host': app.config['db_host'],
        'db_port': app.config['db_port'],
        'db_user': app.config['db_user'],
        'ci_ref_db': app.config['db_ci_ref_db'],
        'spare_prefix': get_provision_param(project, 'spare_prefix'),
        'template_user': get_provision_param(project, 'template_user'),
        'template_prefix': get_provision_param(project, 'template_prefix')
    }


@app.before_request
def before_request():
    token = app.config['service_token']
    gitlab_token = request.headers.get('X-Gitlab-Token')
    if not token or gitlab_token != token:
        app.logger.error('invalid X-Gitlab-Token')
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
        spare_prefix = get_provision_param(project_name, 'spare_prefix')
    if not template_user:
        template_user = get_provision_param(project_name, 'template_user')
    if not template_prefix:
        template_prefix = get_provision_param(project_name, 'template_prefix')

    spare_number = int(spare_last_number(cr, project_name)) + 1
    spare_db = '%s%s_%02i' % (
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
def spare_pool_task(project_name, params):

    spare_pool = params['spare_pool']
    db_template = params['db_template']
    db_host = params['db_host']
    db_port = params['db_port']
    db_user = params['db_user']
    spare_prefix = params['spare_prefix']
    template_user = params['template_user']
    template_prefix = params['template_prefix']

    try:
        conn = None

        def spare_count(cr, project_name):
            prefix = 'spare_%s%%' % project_name
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
        pass
    finally:
        if conn:
            conn.close()


@app.route(PATH_ADD_DB, methods=['POST'])
def add_db():
    db_name = None
    merge_request = request.get_json()
    g.merge_request = merge_request
    attributes = merge_request['object_attributes']
    state = attributes['state']
    for label in merge_request.get('labels', []):
        if label['title'] == app.config['service_ci_label'] \
                and state == 'opened':
            project_name = merge_request['project']['name']
            project_id = merge_request['project']['id']
            merge_id = attributes['iid']
            merge_commit = attributes['last_commit']['id']
            source_branch = attributes['source_branch']
            test_url = '%s.%s' % (
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

                    last_number = spare_last_number(cr, project_name)
                    if last_number:
                        spare_number = int(last_number)
                    else:
                        spare_number = int(spare_create(cr, project_name))

                    db_spare = '%s%02i' % (
                        get_provision_param(project_name, 'spare_prefix'),
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
                raise
                abort(500)
            finally:
                if conn:
                    conn.close()
            break

    if not db_name:
        abort(404)

    return db_name


@celery.task
def refresh_task(project_name, params):
    try:
        conn = None
        template_prefix = params['spare_prefix']
        prefix = '%s%s_%%' % (
            template_prefix,
            project_name,
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


@app.route(PATH_REFRESH_DB, methods=['GET'])
def refresh_db(project_name):
    app.logger.info('triggering refeshing spare databases "%s" project' % (
        project_name
    ))
    params = get_celery_params(app)
    return '%s\n' % str(refresh_task.delay(project_name, params))


@app.route(PATH_APPS_MAP, methods=['GET'])
def apps_map(format_):
    cr, conn = get_cursor(app.config['db_ci_ref_db'])
    cr.execute('''
        SELECT
            project,
            merge_test_url, backend_name,
            merge_id||'_'||merge_commit||' '||merge_date
        FROM merge_request
        WHERE backend_name IS NOT NULL
        ORDER BY merge_date DESC
    ''')

    map_entries = []
    backend_done = []
    for project, url, backend, comment in cr.fetchall():
        if backend not in backend_done:
            if format_ == 'ports':
                ref = url.replace(
                    '.' + get_provision_param(project, 'test_url_suffix'),
                    ''
                )
                backend_port = int(backend.split('_')[-1:][0])
                map_entries.append(u'%s %s' % (
                    '/%s' % ref, backend_port
                ))
            else:
                map_entries.append(u'%s %s # %s' % (
                    url, backend, comment
                ))
            backend_done.append(backend)
    return '\n'.join(map_entries) + '\n'


@app.route(PATH_UPDATE_APPS_MAP, methods=['GET'])
def update_apps_map(db_name):
    cr, conn = get_cursor(app.config['db_ci_ref_db'])
    cr.exectute('''
        SELECT
            project,
        FROM merge_request
        WHERE merge_id||'_'||merge_commit=%s
    ''', (db_name,))
    project = cr.fetchone()

    ref_name = request.args.get('ref_name')
    test_url = '%s.%s' % (
        ref_name, get_provision_param(project, 'test_url_suffix')
    )

    def get_fifo_backend(elements, new_merge_id):

        q = Queue.PriorityQueue()

        merge_already_tested = False
        for id_, merge_id, merge_commit, merge_date, backend in elements:

            count = sum(1 for e in elements if e[1] == merge_id and backend)
            priority = get_priority(
                merge_id, new_merge_id, count, len(elements)+1
            )

            q.put(Backend(id_, test_url, backend, priority))

            if merge_id == new_merge_id:
                # keep only one review app per merge request
                merge_already_tested = True

        if merge_already_tested or \
                q.qsize() >= get_provision_param(project, 'max_test_backend'):
            # evict the oldest backend
            last_backend = q.get()
            last_backend_name = last_backend.backend_name
            last_backend_id = last_backend.id
        else:
            # search the first free backend
            max_backend = get_provision_param(project, 'max_test_backend')
            for backend_num in range(1, max_backend + 1):
                name = '%s%i' % (
                    get_provision_param(project, 'test_backend_prefix'),
                    get_provision_param(project, 'test_backend_base_port') +
                    backend_num
                )

                last_backend_id = None
                last_backend_name = name
                for id_, merge_id, merge_commit, merge_date, backend_name in \
                        elements:
                    if name == backend_name:
                        last_backend_name = name
                        last_backend_id = id_
                        break

                # if free
                if not last_backend_id:
                    break

        return last_backend_id, last_backend_name

    try:
        cr, conn = get_cursor(app.config['db_ci_ref_db'])
        cr.execute('BEGIN')
        merge_id, merge_commit = db_name.split('_')
        merge_id = int(merge_id)
        cr.execute('''
            SELECT id, merge_id, merge_commit, merge_date, backend_name
            FROM merge_request
            WHERE backend_name IS NOT NULL
            ORDER BY merge_date
        ''')
        elements = []
        for values in cr.fetchall():
            elements.append(values)

        id_, backend_name = get_fifo_backend(elements, merge_id)
        if id_:
            cr.execute('''
                UPDATE merge_request SET backend_name=NULL WHERE id=%s
            ''', (id_,))

        cr.execute('''
            UPDATE merge_request SET merge_test_url=%s, backend_name=%s
            WHERE
                id=(
                    SELECT id from merge_request
                    WHERE merge_id=%s AND merge_commit=%s
                    ORDER by merge_date desc
                    LIMIT 1
                )
        ''', (test_url, backend_name, merge_id, merge_commit))
        cr.execute('COMMIT')
        results = []
        results.append('BACKEND_NAME=%s' % backend_name)
        backend_port = int(backend_name.split('_')[-1:][0])
        results.append('BACKEND_PORT=%i' % backend_port)
        return ' '.join(results)

    except:
        app.logger.error('''error setting backend_name for the
            merge_id=%s merge_commit=%s for provision
        ''' % (merge_id, merge_commit))
        cr.execute('ROLLBACK')
        raise
        return 'KO'


@celery.task
def drop_task(db_name, params):
    try:
        conn = None
        merge_id, merge_commit = db_name.split('_')
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
        raise
        app.logger.error('error droping database "%s" project' % (
            db_name
        ))
    finally:
        if conn:
            conn.close()


@app.route(PATH_DROP_DB, methods=['GET'])
def drop_db(db_name):
    app.logger.info('triggering drop database "%s"' % db_name)
    params = get_celery_params(app)
    return '%s\n' % str(drop_task.delay(db_name, params))


@retry(stop_max_delay=60*60*1000, wait_fixed=500)
def wait_db(db_name):
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


@app.route(PATH_GET_DB, methods=['GET'])
def get_db(commit):
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
        test_url = rows[0][2]
        project = rows[0][3]

        wait_db(db)

        result = []
        result.append('DB_NAME=' + db)

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


def create_app():
    return app
