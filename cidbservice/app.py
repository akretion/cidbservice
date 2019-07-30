# /usr/bin/env python2
import json

from flask import Flask, request, g, abort
from . import config
from .services.db import DbService
from .services.port_mapping import PortMappingService

CONFIG_FILE = '/etc/cidbservice.conf'

app = Flask(__name__)
app.config['init_done'] = False

db_service = DbService()
port_mapping_service = PortMappingService()

@app.route('/add_db', methods=['POST'])
def add_db():
    return db_service.add_db()


@app.route('/refresh_db/<project_name>', methods=['GET'])
def refresh_db(project_name):
    return db_service.refresh_db(project_name)


@app.route('/drop_db/<project_name>/<db_name>', methods=['GET'])
def drop_db(project_name, db_name):
    return db_service.drop_db(project, db_name)


@app.route('/get_db/<commit>', methods=['GET'])
def get_db(commit):
    return db_service.get_db(commit)


@app.route('/apps_map/<format_>', methods=['GET'])
def apps_map(format_):
    return port_mapping_service.apps_map(format_)


@app.route('/update_apps_map/<db_name>', methods=['GET'])
def update_apps_map(db_name):
    return port_mapping_service.update_apps_map(db_name)


@app.before_first_request
def init():
    config.parse(app, CONFIG_FILE)
    config.setup_service(app)


@app.before_request
def before_request():
    token = app.config['service_token']
    gitlab_token = request.headers.get('X-Gitlab-Token')
    if not token or gitlab_token != token:
        app.logger.error('invalid X-Gitlab-Token')
        abort(404)


def create_app():
    return app


if not app.config.get('init_done'):
    init()
