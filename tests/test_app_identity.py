from __future__ import annotations

from main import (
    APP_APPLICATION_NAME,
    APP_DISPLAY_NAME,
    APP_ORGANIZATION_NAME,
    configure_application_identity,
)


def test_configure_application_identity_sets_bui_qt_metadata(qt_app):
    configure_application_identity(qt_app)

    assert APP_ORGANIZATION_NAME == "BUI"
    assert APP_APPLICATION_NAME == "BUI"
    assert APP_DISPLAY_NAME == "BUI"
    assert qt_app.organizationName() == "BUI"
    assert qt_app.applicationName() == "BUI"
    assert qt_app.applicationDisplayName() == "BUI"
