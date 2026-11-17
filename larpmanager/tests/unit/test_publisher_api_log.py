# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
"""Unit tests for the logging of the publisher API accesses."""

import json
from unittest.mock import patch

from django.test import RequestFactory

from larpmanager.models.base import PublisherApiKey
from larpmanager.models.miscellanea import Log
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.publication.api import log_api_access


class TestPublisherApiLog(BaseTestCase):
    """Tests that each publisher API access is logged under the system member."""

    def test_access_is_logged_and_counted(self) -> None:
        """A log entry is created and the key usage is updated, without notifying the admins."""
        api_key = PublisherApiKey.objects.create(name="Test key")
        request = RequestFactory().get("/api/publisher/events/", REMOTE_ADDR="10.0.0.1")

        with patch("larpmanager.utils.publication.api.notify_admins") as mock_notify:
            log_api_access(api_key, request, 200, events_count=3)
            log_api_access(api_key, request, 200)

        mock_notify.assert_not_called()
        logs = Log.objects.filter(cls="PublisherAPI", eid=api_key.id)
        assert logs.count() == 2
        assert len({log.member_id for log in logs}) == 1
        assert json.loads(logs.order_by("id").first().dct)["events_count"] == 3
        api_key.refresh_from_db()
        assert api_key.usage_count == 2
        assert api_key.last_used is not None
