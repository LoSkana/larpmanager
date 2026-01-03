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

import logging
from typing import Any, ClassVar

from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import BaseModelForm
from larpmanager.forms.utils import EventCharacterS2WidgetMulti
from larpmanager.models.inventory import Inventory, PoolTypeCI
from larpmanager.models.writing import Character

log = logging.getLogger(__name__)


class InventoryBaseForm(BaseModelForm):
    """Base form for inventory management."""

    class Meta:
        model = Inventory
        exclude = ("number",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the inventory base form."""
        super().__init__(*args, **kwargs)


class OrgaInventoryForm(InventoryBaseForm):
    """Form for organization-level inventory management with character selection."""

    load_js: ClassVar[list[str]] = ["characters-choices"]

    page_title = _("Inventories")
    page_info = _("This page allows you to add or edit a character inventory")

    class Meta:
        model = Inventory
        exclude = ("number",)
        widgets: ClassVar[dict[str, type]] = {
            "owners": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form and configure character selection based on event."""
        super().__init__(*args, **kwargs)

        # Resolve event from instance or params
        event = getattr(self.instance, "event", None) or self.params.get("event", None)

        if event:
            # Set event on the widget so it can filter characters properly
            self.fields["owners"].widget.set_event(event)

            # Set initial queryset and selection
            self.fields["owners"].queryset = Character.objects.filter(event=event)
            if self.instance.pk:
                self.fields["owners"].initial = self.instance.owners.all()
        else:
            # No event → empty queryset
            self.fields["owners"].queryset = Character.objects.none()


class OrgaPoolTypePxForm(BaseModelForm):
    """Form for managing character inventory pool types."""

    page_title = _("Pool type")

    page_info = _("This page allows you to add or edit a ci pool type")

    class Meta:
        model = PoolTypeCI
        exclude = ("number",)
