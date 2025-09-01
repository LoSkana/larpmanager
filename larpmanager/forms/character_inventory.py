# LarpManager - https://larpmanager.com
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

from django import forms
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm

class CharacterInventoryBaseForm(MyForm):
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class OrgaCharacterInventoryForm(CharacterInventoryBaseForm):
    ##load_js = ["characters-choices"]

    page_title = _("Inventories")

    page_info = _("This page allows you to add or edit a character inventory")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)