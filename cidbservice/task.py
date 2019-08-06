# -*- coding: utf-8 -*-

from celery import Celery
from celery.utils.log import get_task_logger

from .tools import config, cursor, get_spare, spare_create

logger = get_task_logger(__name__)

celery = Celery("cidbservice", broker=config["celery"]["broker"])

TASK_KWARGS = {
    "autoretry_for": (Exception,),
    "retry_kwargs": {"max_retries": 5, "countdown": 5},
}


@celery.task(**TASK_KWARGS)
def spare_pool_task(project_name):
    with cursor() as cr:
        spare_pool = config["projects"][project_name]["spare_pool"]
        while True:
            count = len(get_spare(cr, project_name))
            if count >= spare_pool:
                logger.info(
                    "spare pool ok for %s (%i/%i)"
                    % (project_name, count, spare_pool)
                )
                break
            else:
                spare_create(cr, project_name)


@celery.task(**TASK_KWARGS)
def refresh_task(project_name):
    with cursor() as cr:
        for spare in get_spare(cr, project_name):
            logger.info("Drop spare database {}".format(spare))
            cr.execute("DROP DATABASE IF EXISTS {}".format(spare))
        spare_pool_task.delay(project_name)
