"""Optional runnable app that mounts Account 3 feature routers.

Account 9 owns production integration in app.main. This shim keeps that file
untouched while allowing the Account 3 feature branch to be run and reviewed.
When merging, Account 9 should register these routers in the canonical app and
may then retire this module.
"""

from app.main import app
from app.routers.actions import router as actions_router
from app.routers.scenarios import router as scenarios_router

_prefix = app.state.settings.api_prefix
app.include_router(actions_router, prefix=_prefix)
app.include_router(scenarios_router, prefix=_prefix)

app.description = (
    "CampusTwin AI backend core plus Account 3 simulator, explainable detection "
    "rules, auditable action workflow, and independent verification."
)
