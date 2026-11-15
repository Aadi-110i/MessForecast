"""Role -> capability mapping.

The specification states the permissions per role. Keeping them in one table
means the API, the templates and the management commands all agree, and a role
change is a single edit.

Capability list
---------------
VIEW_MENU                 student, kitchen staff, mess manager, mess admin, finance, admin
VIEW_OWN_ATTENDANCE       student
RECORD_ATTENDANCE         kitchen staff, mess manager, mess admin, admin
MANAGE_MASTERS            mess admin, admin
PLAN_MENU                 mess manager, mess admin, admin
VIEW_FORECAST             kitchen staff, mess manager, mess admin, finance, admin
RECORD_ACTUALS            kitchen staff, mess manager, admin
VIEW_WASTE_COST           mess manager, mess admin, finance, admin
CONFIGURE_SERVICE_LEVEL   mess manager, admin
CONFIGURE_FORECAST        admin
MANAGE_HALLS              mess admin, admin
VIEW_ACCURACY             mess manager, finance, admin
VIEW_PREPARATION_PLAN     kitchen staff, mess manager, mess admin, finance, admin
PUBLISH_MENU              mess manager, mess admin, admin
MANAGE_USERS              mess admin, admin
"""

from .models import User

CAPABILITIES: dict[str, set[str]] = {
    User.Role.STUDENT: {
        "VIEW_MENU",
        "VIEW_OWN_ATTENDANCE",
    },
    User.Role.KITCHEN_STAFF: {
        "VIEW_MENU",
        "RECORD_ATTENDANCE",
        "VIEW_FORECAST",
        "VIEW_PREPARATION_PLAN",
        "RECORD_ACTUALS",
    },
    User.Role.MESS_MANAGER: {
        "VIEW_MENU",
        "RECORD_ATTENDANCE",
        "PLAN_MENU",
        "PUBLISH_MENU",
        "VIEW_FORECAST",
        "VIEW_PREPARATION_PLAN",
        "RECORD_ACTUALS",
        "VIEW_WASTE_COST",
        "CONFIGURE_SERVICE_LEVEL",
        "VIEW_ACCURACY",
    },
    User.Role.MESS_ADMIN: {
        "VIEW_MENU",
        "RECORD_ATTENDANCE",
        "MANAGE_MASTERS",
        "PLAN_MENU",
        "PUBLISH_MENU",
        "VIEW_FORECAST",
        "VIEW_PREPARATION_PLAN",
        "VIEW_WASTE_COST",
        "MANAGE_HALLS",
        "MANAGE_USERS",
    },
    User.Role.FINANCE_OFFICER: {
        "VIEW_MENU",
        "VIEW_FORECAST",
        "VIEW_PREPARATION_PLAN",
        "VIEW_WASTE_COST",
        "VIEW_ACCURACY",
    },
    User.Role.ADMINISTRATOR: {
        "VIEW_MENU",
        "RECORD_ATTENDANCE",
        "MANAGE_MASTERS",
        "PLAN_MENU",
        "PUBLISH_MENU",
        "VIEW_FORECAST",
        "VIEW_PREPARATION_PLAN",
        "RECORD_ACTUALS",
        "VIEW_WASTE_COST",
        "CONFIGURE_SERVICE_LEVEL",
        "CONFIGURE_FORECAST",
        "MANAGE_HALLS",
        "VIEW_ACCURACY",
        "MANAGE_USERS",
    },
}


def has_capability(user, capability: str) -> bool:
    """True when ``user`` holds ``capability``."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return capability in CAPABILITIES.get(user.role, set())
