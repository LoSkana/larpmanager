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

"""Tests for the demo association clone engine."""

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.utils import timezone

from larpmanager.fixtures.demos import DEMO_BUILDERS
from larpmanager.models.accounting import AccountingItemPayment, PaymentInvoice
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.larpmanager import LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.miscellanea import EmailContent
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.writing import Character, Faction, Relationship
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.services.demo import clone_association

def test_clone_every_registered_demo() -> None:
    """Each registered demo builder produces a template that clones without error."""

    for builder in DEMO_BUILDERS:
        demo_type = builder()
        template = demo_type.template_association

        clone = clone_association(demo_type, f"clone-{demo_type.slug}", template.skin_id)

        assert clone.pk != template.pk
        assert clone.slug == f"clone-{demo_type.slug}"
        assert clone.demo_type_id == demo_type.pk

        assert (
            Event.objects.filter(association=clone).count()
            == Event.objects.filter(association=template).count()
        )
        assert (
            Character.objects.filter(event__association=clone).count()
            == Character.objects.filter(event__association=template).count()
        )
        assert (
            Registration.objects.filter(run__event__association=clone).count()
            == Registration.objects.filter(run__event__association=template).count()
        )
        assert (
            Membership.objects.filter(association=clone).count()
            == Membership.objects.filter(association=template).count()
        )
