import pytest
from fastapi.routing import APIRoute

from app.dependencies import require_admin_csrf, require_admin_event_access
from app.routers import (
    admin,
    admin_accounts,
    admin_coupons,
    admin_events,
    admin_participant_import,
    admin_participants,
    admin_vendors,
    admin_wallets,
)

FEATURE_ROUTERS = [
    admin_accounts.router,
    admin_events.router,
    admin_participants.router,
    admin_participant_import.router,
    admin_wallets.router,
    admin_vendors.router,
    admin_coupons.router,
]
FEATURE_ROUTES = [
    route
    for router in FEATURE_ROUTERS
    for route in router.routes
    if isinstance(route, APIRoute)
]


@pytest.mark.parametrize("feature_route", FEATURE_ROUTES, ids=lambda route: route.name)
def test_feature_routes_keep_paths_handlers_and_legacy_imports(feature_route: APIRoute) -> None:
    assembled = next(
        route
        for route in admin.router.routes
        if isinstance(route, APIRoute)
        and route.path == f"/admin{feature_route.path}"
        and route.methods == feature_route.methods
    )
    assert assembled.endpoint is feature_route.endpoint
    assert getattr(admin, feature_route.endpoint.__name__) is feature_route.endpoint


@pytest.mark.parametrize(
    "route",
    [route for route in admin.router.routes if isinstance(route, APIRoute)],
    ids=lambda route: route.name,
)
def test_admin_routes_keep_inherited_event_access_guard(route: APIRoute) -> None:
    assert any(
        dependency.call is require_admin_event_access
        for dependency in route.dependant.dependencies
    )


@pytest.mark.parametrize(
    "route",
    [route for route in FEATURE_ROUTES if route.methods & {"POST", "PUT", "PATCH", "DELETE"}],
    ids=lambda route: route.name,
)
def test_moved_write_routes_keep_csrf_validation(route: APIRoute) -> None:
    assert any(dependency.call is require_admin_csrf for dependency in route.dependant.dependencies)
