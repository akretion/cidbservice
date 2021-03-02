# -*- coding: utf-8 -*-
import requests


def _parse_md_table(md_table):
    result = {}
    lines = md_table.split("\n")
    for i, line in enumerate(lines):
        if i <= 1:
            continue
        else:
            key = False
            value = False
            for j, cell in enumerate(line.split("|")):
                if j == 1:
                    key = cell.strip()
                elif j == 2:
                    value = cell.strip()
            result[key] = value
    return result


class MrService(object):
    def __init__(self, logger, config):
        super(MrService, self).__init__()
        self.config = config
        self.logger = logger

    def environment(self, project_name, mr_number):
        project_config = self.config["projects"][project_name]
        if not project_config.get("gitlab_project_id"):
            raise Exception(
                "Missing key '%s' in project %s"
                % ("gitlab_project_id", project_name)
            )
        project_id = self.config["projects"][project_name]["gitlab_project_id"]
        url = ("{}/api/v4/projects/{}/merge_requests/{}").format(
            self.config["gitlab"]["host"], project_id, mr_number
        )
        headers = {"Private-Token": self.config["gitlab"]["token"]}
        self.logger.info(
            "fetching gitlab MR description (project: {}, mr: {})".format(
                project_id, mr_number
            )
        )
        res = requests.get(url, headers=headers)
        description = res.json()["description"]
        md_table = description.split("---\n")[
            -1
        ]  # last substring after "---" separator
        return _parse_md_table(md_table)
