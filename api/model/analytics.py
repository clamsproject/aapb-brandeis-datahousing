"""

Analyzing the contents of the MMIF storage.

"""

import json
import os
import re

from api import STORAGE_DIR


def storage_analytics() -> dict:
    """
    Provide analytics and status information about the current MMIF storage system.
    This method returns info on the total number of MMIF files, number of unique
    workflows, app parameters, non-terminal MMIFs, and dirty workflow MMIFs.
    """

    # TODO (ledibr @ 10/12/25): consider adding params to show/hide certain parts
    # e.g. full workflow specs?

    analytics = {"total_mmif_files": 0, "total_workflows": 0, "workflows": [],
                "non_terminal_mmif_count": 0, "dirty_workflow_mmif_count": 0}
    app_specs = {}

    for root, dirs, files in os.walk(STORAGE_DIR):
        #if current_app.config.get('DEBUG'):
        #    print("Root:", root)
        #    print("dirs:", dirs)
        #    print("files:", files)

        curr_workflow = root[root.index(STORAGE_DIR) + len(STORAGE_DIR):]
        curr_workflow = curr_workflow.lstrip('/')

        json_list = [f for f in files if re.search(r'\.json$', f)]
        for subdir in dirs:
            config = subdir + '.json'
            if config in json_list:
                curr_app = curr_workflow[curr_workflow.rfind('/', 0, curr_workflow.rfind('/'))+1:]
                full_path = os.path.join(curr_app, subdir)
                with open(os.path.join(root, config), 'r') as f:
                    app_specs[full_path] = json.load(f)
                if len(app_specs[full_path]) == 0:
                    app_specs[full_path] = {}
        mmif_list = [f for f in files if re.search(r'\.mmif$', f)]
        if mmif_list:
            analytics["total_mmif_files"] += len(mmif_list)
            analytics["total_workflows"] += 1

            workflow_stats = {"path": curr_workflow, "spec": {}, "mmif_count": len(mmif_list)}
            segments = curr_workflow.split("/")
            curr_apps = ["/".join(segments[i:i + 3]) for i in range(0, len(segments), 3)]
            for i, app in enumerate(curr_apps):
                if app in app_specs:
                    workflow_stats["spec"][app] = app_specs[app]
            analytics["workflows"].append(workflow_stats)

            if re.search(r'-dirty', curr_workflow):
                analytics["dirty_workflow_mmif_count"] += len(mmif_list)
            if dirs:
                analytics["non_terminal_mmif_count"] += len(mmif_list)

    # TODO (ledibr @ 10/27/25): the analytics seem to be in alphabetical key order,
    # not chronological. given how long these might get, do we want to potentially
    # return this differently?

    return analytics
