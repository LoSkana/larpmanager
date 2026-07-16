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

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.utils import timezone

from larpmanager.models.accounting import AccountingItemPayment, PaymentInvoice
from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, Run
from larpmanager.models.larpmanager import LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.miscellanea import EmailContent
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.writing import Character, Faction, Relationship
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.services.demo import clone_association


class TestCloneAssociation(BaseTestCase):
    """Tests for clone_association deep copy."""

    def setUp(self) -> None:
        """Build a small but complete template association graph."""
        self.template = Association.objects.create(name="Template Org", slug="tmplorg")

        template_user = User.objects.create(username="tmpl-player", email="tmpl-player@demo.it")
        self.template_member = template_user.member
        self.template_member.name = "Template"
        self.template_member.surname = "Player"
        self.template_member.save()
        Membership.objects.create(
            member=self.template_member, association=self.template, status=MembershipStatus.JOINED
        )

        self.event = Event.objects.create(association=self.template, name="Template Event", slug="tmplevent")
        self.run = Run.objects.filter(event=self.event).first()
        self.run.start = date(2020, 6, 1)
        self.run.end = date(2020, 6, 3)
        self.run.save()

        self.event_ticket = RegistrationTicket.objects.filter(event=self.event).first()
        self.character_one = self.character(event=self.event, name="Hero")
        self.character_two = self.character(event=self.event, name="Villain")
        Relationship.objects.create(source=self.character_one, target=self.character_two, text="Nemesis")
        self.faction = Faction.objects.create(event=self.event, name="Guild", number=1)
        self.faction.characters.add(self.character_one)

        self.registration = Registration.objects.create(
            run=self.run,
            member=self.template_member,
            ticket=self.event_ticket,
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("50.00"),
        )
        self.invoice = self.payment_invoice(member=self.template_member, association=self.template)
        self.invoice.save()
        AccountingItemPayment.objects.create(
            member=self.template_member,
            association=self.template,
            registration=self.registration,
            inv=self.invoice,
            value=Decimal("50.00"),
        )

        self.demo_type = LarpManagerDemoType.objects.create(
            name="Fantasy", slug="fantasy", template_association=self.template
        )

    def test_clone_full_graph(self) -> None:
        """Clone copies the whole graph, remaps FKs and regenerates unique fields."""
        emails_before = EmailContent.objects.count()

        clone = clone_association(self.demo_type, "test-clone", self.template.skin_id)

        assert clone.pk != self.template.pk
        assert clone.slug == "test-clone"
        assert clone.demo_type_id == self.demo_type.pk
        assert clone.lite_mode is False
        assert clone.uuid and clone.uuid != self.template.uuid

        # Events and runs copied with shifted dates
        cloned_events = Event.objects.filter(association=clone)
        assert cloned_events.count() == Event.objects.filter(association=self.template).count()
        cloned_run = Run.objects.get(event__association=clone)
        expected_start = timezone.now().date() + relativedelta(months=1)
        assert cloned_run.start == expected_start
        assert cloned_run.end - cloned_run.start == self.run.end - self.run.start
        assert cloned_run.registration_secret != self.run.registration_secret

        # Members duplicated, not shared
        cloned_memberships = Membership.objects.filter(association=clone)
        assert cloned_memberships.count() == Membership.objects.filter(association=self.template).count()
        cloned_member_ids = set(cloned_memberships.values_list("member_id", flat=True))
        template_member_ids = set(
            Membership.objects.filter(association=self.template).values_list("member_id", flat=True)
        )
        assert not cloned_member_ids & template_member_ids

        # Registration remapped to cloned run/member/ticket, created shifted by delta
        cloned_registration = Registration.objects.get(run__event__association=clone)
        assert cloned_registration.run_id == cloned_run.pk
        assert cloned_registration.member_id in cloned_member_ids
        assert cloned_registration.ticket.event.association_id == clone.pk
        assert cloned_registration.tot_payed == self.registration.tot_payed
        delta = expected_start - self.run.start
        assert cloned_registration.created.date() == (self.registration.created + delta).date()

        # Characters, relationships and factions remapped inside the clone
        cloned_characters = Character.objects.filter(event__association=clone)
        assert cloned_characters.count() == 2
        cloned_character_ids = set(cloned_characters.values_list("pk", flat=True))
        cloned_relationship = Relationship.objects.get(source__event__association=clone)
        assert cloned_relationship.source_id in cloned_character_ids
        assert cloned_relationship.target_id in cloned_character_ids
        cloned_faction = Faction.objects.get(event__association=clone)
        faction_character_ids = set(cloned_faction.characters.values_list("pk", flat=True))
        assert faction_character_ids and faction_character_ids <= cloned_character_ids

        # Accounting cloned with regenerated invoice code
        cloned_invoice = PaymentInvoice.objects.get(association=clone)
        assert cloned_invoice.cod != self.invoice.cod
        cloned_payment = AccountingItemPayment.objects.get(association=clone)
        assert cloned_payment.registration_id == cloned_registration.pk
        assert cloned_payment.inv_id == cloned_invoice.pk
        assert cloned_payment.value == Decimal("50.00")

        # No notification emails generated by the clone
        assert EmailContent.objects.count() == emails_before

    def test_clone_keeps_association_features(self) -> None:
        """Clone keeps the template's association-level features, even ones outside the skin's defaults.

        Association.save() has a post-save hook that resets features to the skin's default_features
        via transaction.on_commit; it must be suppressed during clone or it silently strips any
        template feature (e.g. expenses) that isn't part of the skin defaults.
        """
        feature = Feature.objects.create(name="Expenses", slug="expenses-clone-test")
        self.template.features.add(feature)

        with self.captureOnCommitCallbacks(execute=True):
            clone = clone_association(self.demo_type, "test-clone-features", self.template.skin_id)

        assert feature.pk in set(clone.features.values_list("pk", flat=True))

    def test_clone_without_run_dates(self) -> None:
        """Cloning a template without dated runs applies no date shift."""
        self.run.start = None
        self.run.end = None
        self.run.save()

        clone = clone_association(self.demo_type, "test-clone-nodates", self.template.skin_id)

        cloned_run = Run.objects.get(event__association=clone)
        assert cloned_run.start is None
        assert cloned_run.end is None
        cloned_registration = Registration.objects.get(run__event__association=clone)
        assert cloned_registration.created.date() == self.registration.created.date()
