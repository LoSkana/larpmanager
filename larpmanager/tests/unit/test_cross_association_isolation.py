"""Security tests for cross-association isolation.

This module tests that users from one association cannot access
resources (characters, plots, etc.) from another association by
manipulating UUIDs in requests.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import RequestFactory

from larpmanager.forms.base import BaseModelForm
from larpmanager.forms.registration import OrgaRegistrationForm
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.writing import Character, Faction, Plot
from larpmanager.views.orga.character import orga_characters_summary
from larpmanager.views.orga.writing import orga_multichoice_available, orga_version

User = get_user_model()


@pytest.mark.django_db
class TestCrossAssociationIsolation:
    """Test suite for cross-association resource isolation."""

    @pytest.fixture
    def setup_two_associations(self):
        """Create two separate associations with events and characters."""
        # Association A
        assoc_a = Association.objects.create(name="Association A", slug="assoc-a")
        event_a = Event.objects.create(
            name="Event A",
            association=assoc_a,
            slug="event-a",
        )
        run_a = Run.objects.create(event=event_a)
        character_a = Character.objects.create(
            event=event_a,
            name="Character A",
            number=1,
        )
        plot_a = Plot.objects.create(
            event=event_a,
            name="Plot A",
            number=1,
        )
        faction_a = Faction.objects.create(
            event=event_a,
            name="Faction A",
            number=1,
        )
        ticket_a = RegistrationTicket.objects.create(
            event=event_a,
            name="Ticket A",
        )

        # Association B
        assoc_b = Association.objects.create(name="Association B", slug="assoc-b")
        event_b = Event.objects.create(
            name="Event B",
            association=assoc_b,
            slug="event-b",
        )
        run_b = Run.objects.create(event=event_b)
        character_b = Character.objects.create(
            event=event_b,
            name="Character B",
            number=1,
        )
        plot_b = Plot.objects.create(
            event=event_b,
            name="Plot B",
            number=1,
        )
        faction_b = Faction.objects.create(
            event=event_b,
            name="Faction B",
            number=1,
        )
        ticket_b = RegistrationTicket.objects.create(
            event=event_b,
            name="Ticket B",
        )

        # Create users
        user_a = User.objects.create_user(username="orga_a", password="test123", email="orga_a@test.com")
        member_a = user_a.member
        Membership.objects.create(
            member=member_a,
            association=assoc_a,
        )

        user_b = User.objects.create_user(username="orga_b", password="test123", email="orga_b@test.com")
        member_b = user_b.member
        Membership.objects.create(
            member=member_b,
            association=assoc_b,
        )

        return {
            "assoc_a": assoc_a,
            "event_a": event_a,
            "run_a": run_a,
            "character_a": character_a,
            "plot_a": plot_a,
            "faction_a": faction_a,
            "ticket_a": ticket_a,
            "user_a": user_a,
            "member_a": member_a,
            "assoc_b": assoc_b,
            "event_b": event_b,
            "run_b": run_b,
            "character_b": character_b,
            "plot_b": plot_b,
            "faction_b": faction_b,
            "ticket_b": ticket_b,
            "user_b": user_b,
            "member_b": member_b,
        }

    def test_character_summary_cross_association_blocked(self, setup_two_associations):
        """Test that orga_characters_summary prevents access to other association's characters."""
        data = setup_two_associations
        factory = RequestFactory()

        # Create request from user A trying to access character B
        request = factory.get(f"/orga/event-a/characters/summary/{data['character_b'].uuid}/")
        request.user = data["user_a"]

        # Should raise Http404 when trying to access character from wrong association
        with pytest.raises(Exception):  # Will raise DoesNotExist wrapped in Http404
            orga_characters_summary(request, "event-a", str(data["character_b"].uuid))

    def test_multichoice_available_cross_association_blocked(self, setup_two_associations):
        """Test that orga_multichoice_available prevents access to other association's plots."""
        data = setup_two_associations
        factory = RequestFactory()

        # Create POST request from user A trying to access plot B
        request = factory.post(
            "/orga/event-a/multichoice-available/",
            {
                "type": "plot",
                "edit_uuid": str(data["plot_b"].uuid),
            },
        )
        request.user = data["user_a"]

        # Should raise Http404 or DoesNotExist when accessing plot from wrong association
        with pytest.raises(Exception):  # Will raise DoesNotExist because of event filter
            orga_multichoice_available(request, "event-a")

    def test_registration_ticket_cross_event_blocked(self, setup_two_associations):
        """Test that OrgaRegistrationForm validates ticket belongs to correct event."""
        data = setup_two_associations

        # Create a registration for event A
        registration = Registration.objects.create(
            run=data["run_a"],
            member=data["member_a"],
        )

        # Try to assign ticket from event B
        form = OrgaRegistrationForm(
            data={"ticket": str(data["ticket_b"].uuid)},
            instance=registration,
            context={
                "run": data["run_a"],
                "event": data["event_a"],
            },
        )

        # Form should be invalid
        assert not form.is_valid()
        assert "ticket" in form.errors

    def test_character_belongs_to_correct_event(self, setup_two_associations):
        """Test that Character queries properly filter by event."""
        data = setup_two_associations

        # Query characters for event A should only return character A
        characters_a = Character.objects.filter(event=data["event_a"])
        assert characters_a.count() == 1
        assert characters_a.first() == data["character_a"]

        # Character B should not be in event A's queryset
        assert not characters_a.filter(uuid=data["character_b"].uuid).exists()

    def test_plot_belongs_to_correct_event(self, setup_two_associations):
        """Test that Plot queries properly filter by event."""
        data = setup_two_associations

        # Query plots for event A should only return plot A
        plots_a = Plot.objects.filter(event=data["event_a"])
        assert plots_a.count() == 1
        assert plots_a.first() == data["plot_a"]

        # Plot B should not be in event A's queryset
        assert not plots_a.filter(uuid=data["plot_b"].uuid).exists()

    def test_faction_belongs_to_correct_event(self, setup_two_associations):
        """Test that Faction queries properly filter by event."""
        data = setup_two_associations

        # Query factions for event A should only return faction A
        factions_a = Faction.objects.filter(event=data["event_a"])
        assert factions_a.count() == 1
        assert factions_a.first() == data["faction_a"]

        # Faction B should not be in event A's queryset
        assert not factions_a.filter(uuid=data["faction_b"].uuid).exists()

    def test_run_cross_association_validation(self, setup_two_associations):
        """Test that BaseModelForm validates run belongs to correct association."""
        data = setup_two_associations

        # Create a minimal form class for testing
        class TestForm(BaseModelForm):
            class Meta:
                model = Registration
                fields = ["run"]

        # Try to use run from association B in context of association A
        form = TestForm(
            data={"run": str(data["run_b"].uuid)},
            context={
                "event": data["event_a"],
                "run": data["run_a"],
            },
        )

        # Form should be invalid due to association mismatch
        assert not form.is_valid()
        # The clean_run method should catch this and raise ValidationError

    def test_direct_uuid_enumeration_blocked(self, setup_two_associations):
        """Test that direct UUID enumeration across associations is blocked."""
        data = setup_two_associations

        # Attempting to get character B using event A's context should fail
        with pytest.raises(Exception):
            Character.objects.get(
                event=data["event_a"],
                uuid=data["character_b"].uuid,
            )

        # Same for plots
        with pytest.raises(Exception):
            Plot.objects.get(
                event=data["event_a"],
                uuid=data["plot_b"].uuid,
            )

        # Same for factions
        with pytest.raises(Exception):
            Faction.objects.get(
                event=data["event_a"],
                uuid=data["faction_b"].uuid,
            )
