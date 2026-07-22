from __future__ import annotations

import pytest

from crop_circle_geo.rights import publication_qualification, require_publication_rights


def test_publication_fails_closed_when_rights_are_incomplete():
    allowed, reasons = publication_qualification({"status": "permission_pending"})
    assert not allowed
    assert "rights_status_not_publication_authorized" in reasons
    with pytest.raises(PermissionError):
        require_publication_rights({"status": "cc_by", "license": "CC BY 4.0"})


def test_complete_open_license_record_qualifies():
    rights = {
        "status": "cc_by", "holder": "Example creator", "license": "CC BY 4.0",
        "proof": "https://example.test/license", "public_derivative_export_allowed": True,
    }
    assert publication_qualification(rights) == (True, [])

