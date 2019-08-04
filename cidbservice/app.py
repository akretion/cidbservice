# /usr/bin/env python2
import json

from flask import Flask, request, g, abort
from .tools import config
from .services.db import DbService
from .services.port_mapping import PortMappingService


app = Flask(__name__)
app.config.update(config)

port_mapping_service = PortMappingService(config)

def check_authentication(project_name):
    token = request.headers.get('X-Gitlab-Token')
    # TODO python 3
    # https://docs.python.org/3/library/hmac.html#hmac.compare_digest
    if token == config['admin']['token']\
            or token == config['projects'][project_name]['token']:
        return True
    else:
        app.logger.error('invalid X-Gitlab-Token')
        abort(401)


@app.route('/db/refresh/<project_name>', methods=['GET'])
def db_refresh(project_name):
    check_authentication(project_name)
    db_service = DbService(app.logger, config)
    return db_service.refresh(project_name)


@app.route('/db/get/<project_name>/<db_name>', methods=['GET'])
def db_get(project_name, db_name):
    check_authentication(project_name)
    db_service = DbService(app.logger, config)
    return db_service.get(project_name, db_name)


@app.route('/apps_map/<format_>', methods=['GET'])
def apps_map(format_):
    return port_mapping_service.apps_map(format_)


@app.route('/update_apps_map/<db_name>', methods=['GET'])
def update_apps_map(db_name):
    return port_mapping_service.update_apps_map(db_name)


#@app.before_first_request
#def init():
    #config.setup_service(app)


#@app.before_request
#def before_request():
#    token = app.config['service_token']
#    gitlab_token = request.headers.get('X-Gitlab-Token')
#    if not token or gitlab_token != token:
#        app.logger.error('invalid X-Gitlab-Token')
#        abort(404)
#

def create_app():
    return app
