#!/usr/bin/env python3
"""Run the legacy PyTracking REST API on CPU for compatibility diagnosis."""

from pytracking.evaluation.tracker import Tracker


_get_parameters = Tracker.get_parameters


def get_cpu_parameters(self):
    params = _get_parameters(self)
    params.use_gpu = False
    if hasattr(params, "net"):
        params.net.use_gpu = False
    return params


Tracker.get_parameters = get_cpu_parameters

from pytracking.server_api import app  # noqa: E402


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=False)
