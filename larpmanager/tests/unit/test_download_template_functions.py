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

"""Tests for CSV template generation used by orga_upload_template"""

import pytest

from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.io.download import _get_column_names, _temp_csv_file
from larpmanager.views.orga.event import _form_template


@pytest.mark.django_db(transaction=True)
class TestFormTemplateFunctions(BaseTestCase):
    """Test cases for _form_template column/row consistency"""

    def _build_context(self, features: set) -> dict:
        context = {"typ": "character_form", "features": features}
        _get_column_names(context)
        return context

    def test_form_template_without_requirements_feature(self) -> None:
        """Sample row length must match header length when requirements feature is off"""
        context = self._build_context(features=set())

        exports = _form_template(context)

        for _name, headers, rows in exports:
            for row in rows:
                self.assertEqual(len(headers), len(row))
            # Building the CSV must not raise (this reproduces the reported bug)
            _temp_csv_file(headers, rows)

    def test_form_template_with_requirements_feature(self) -> None:
        """Sample row length must match header length when the requirements column is added"""
        context = self._build_context(features={"wri_que_requirements"})

        exports = _form_template(context)

        options_export = next(export for export in exports if export[0] == "options")
        _name, headers, rows = options_export

        self.assertIn("requirements", headers)
        for row in rows:
            self.assertEqual(len(headers), len(row))
        # Building the CSV must not raise (this reproduces the reported bug)
        _temp_csv_file(headers, rows)
