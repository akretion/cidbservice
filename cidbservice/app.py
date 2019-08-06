# /usr/bin/env python2

from flask import Flask, abort, request

from .services.db import DbService
from .services.port import PortService
from .tools import config, setup_db

app = Flask(__name__)
app.config.update(config)

db_service = DbService(app.logger, config)
port_service = PortService(app.logger, config)


def check_authentication(project_name):
    token = request.headers.get("X-Gitlab-Token")
    # TODO python 3
    # https://docs.python.org/3/library/hmac.html#hmac.compare_digest
    if (
        token == config["admin"]["token"]
        or token == config["projects"][project_name]["token"]
    ):
        return True
    else:
        app.logger.error("invalid X-Gitlab-Token")
        abort(401)


def check_port_active(project_name):
    if not config["projects"][project_name]["port_mapping_active"]:
        abort(401, "Port routing not active on this project")


def check_db_name(project_name, db_name):
    if not db_name.startswith(project_name):
        return abort(400, "Wrong db name")


@app.route("/db/refresh/<project_name>", methods=["GET"])
def db_refresh(project_name):
    check_authentication(project_name)
    return db_service.refresh(project_name)


@app.route("/db/get/<project_name>/<db_name>", methods=["GET"])
def db_get(project_name, db_name):
    check_authentication(project_name)
    check_db_name(project_name, db_name)
    return db_service.get(project_name, db_name)


@app.route("/port/lock/<project_name>/<db_name>", methods=["GET"])
def port_lock(project_name, db_name):
    check_authentication(project_name)
    check_db_name(project_name, db_name)
    check_port_active(project_name)
    return port_service.lock(project_name, db_name)


@app.route("/port/release/<project_name>/<db_name>", methods=["GET"])
def port_release(project_name, db_name):
    check_authentication(project_name)
    check_db_name(project_name, db_name)
    check_port_active(project_name)
    return port_service.release(project_name, db_name)


@app.route("/port/redirect/<project_name>/<db_name>", methods=["GET"])
def port_redirect(project_name, db_name):
    check_db_name(project_name, db_name)
    check_port_active(project_name)
    return port_service.redirect(project_name, db_name)


@app.before_first_request
def init():
    setup_db()


def create_app():
    return app
