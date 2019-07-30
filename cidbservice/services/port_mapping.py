# /usr/bin/env python2
import Queue


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


class PortMappingService(object):

    def get_priority(merge_id, new_merge_id, count, max_priority=1000):
        if merge_id == new_merge_id:
            return max_priority
        else:
            return count

    def apps_map(format_):
        """Only for Abilis
        Called by HA proxy to get the mapping of port
        for exposing the PR
        """
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
                        '-' + get_provision_param(project, 'test_url_suffix'),
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

    def update_apps_map(self, db_name):
        """Only for Abilis
        Assign a port to the PR as we can not use a domain.
        The port affected will be consumed by HA proxy
        through a cron that call apps_map
        """
        cr, conn = get_cursor(app.config['db_ci_ref_db'])
        cr.execute('''
            SELECT
                project,
            FROM merge_request
            WHERE merge_id||'_'||merge_commit=%s
        ''', (db_name,))
        project = cr.fetchone()

        ref_name = request.args.get('ref_name')
        test_url = '%s-%s' % (
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
                        get_provision_param(project, 'test_backend_base_port'),
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
            return 'KO'
