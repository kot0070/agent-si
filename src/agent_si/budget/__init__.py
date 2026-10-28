"""Project budget gate + usage/cost telemetry (Lane B2).

K04 code over frozen K13 schemas; see gate.py and telemetry.py.

Mounts the frozen budget route into backend.pools_routes.ROUTES
idempotently (backend never imports budget, so there is no cycle).
"""
from agent_si.backend import pools_routes as _pools_routes
from agent_si.budget.routes import BUDGET_ROUTES as _BUDGET_ROUTES


def _mount_budget_routes():
    have = {(str(method).lower(), str(path))
            for method, path, _name, _fn in _pools_routes.ROUTES}
    missing = [row for row in _BUDGET_ROUTES
               if (str(row[0]).lower(), str(row[1])) not in have]
    if not missing:
        return
    _pools_routes.ROUTES = tuple(_pools_routes.ROUTES) + tuple(missing)
    dispatch = getattr(_pools_routes, "_DISPATCH", None)
    if dispatch is not None:
        for method, path, _name, fn in missing:
            dispatch.setdefault((method, path), fn)


_mount_budget_routes()
