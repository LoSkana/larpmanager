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
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.accounting.registration import get_date_surcharge
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.base import BaseRegistrationForm, MyForm
from larpmanager.forms.utils import (
    AllowedS2WidgetMulti,
    AssociationMemberS2Widget,
    DatePickerInput,
    FactionS2WidgetMulti,
    TicketS2WidgetMulti,
)
from larpmanager.models.casting import Trait
from larpmanager.models.form import (
    QuestionStatus,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationQuestionType,
)
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character, Faction
from larpmanager.utils.core.common import get_time_diff_today
from larpmanager.utils.users.registration import get_reduced_available_count

if TYPE_CHECKING:
    from larpmanager.models.event import Event, Run


class RegistrationForm(BaseRegistrationForm):
    """Form for handling event registration with tickets, quotas, and questions."""

    class Meta:
        model = Registration
        fields = ("modified",)
        widgets: ClassVar[dict] = {"modified": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize registration form with tickets, questions, and event-specific options.

        Sets up form fields for event registration including ticket selection,
        quota management, payment options, and registration questions.

        Args:
            *args: Variable length argument list passed to parent constructor.
            **kwargs: Arbitrary keyword arguments passed to parent constructor.
                Expected to contain 'params' with 'run' key containing Run instance
                and 'event' key containing Event instance (accessed via run.event).

        Raises:
            KeyError: If 'params' or 'run' key is missing from kwargs.

        Note:
            The form handles waiting list placement, quota management, payment
            processing, and dynamic question generation based on event configuration.

        """
        # Call parent constructor with all provided arguments
        super().__init__(*args, **kwargs)

        # Initialize core form state variables for tracking form data
        # These store form configuration and user selections
        self.questions = []
        self.tickets_map = {}
        self.profiles = {}
        self.section_descriptions = {}
        self.ticket = None

        # Extract run and event objects from parameters for form configuration
        # These provide context for all subsequent form setup operations
        run = self.params["run"]
        event = run.event
        self.event = event

        # Get current registration counts for quota calculations and availability checks
        # This data determines ticket availability and waiting list status
        reg_counts = get_reg_counts(run)

        # Initialize ticket selection field and retrieve help text for user guidance
        # Creates the primary ticket selection interface with availability info
        ticket_help = self.init_ticket(event, reg_counts, run)

        # Determine if registration should be placed in waiting list based on instance or run status
        # Checks existing registration status or current run capacity
        self.waiting_check = (
            self.instance and self.instance.ticket and self.instance.ticket.tier == TicketTier.WAITING
        ) or (not self.instance and "waiting" in run.status)

        # Initialize quota management system and additional registration options
        # Sets up capacity limits and optional registration features
        self.init_quotas(event, run)
        self.init_additionals()

        # Setup payment-related form fields including pricing and surcharges
        # Configures payment options and calculates total costs
        self.init_pay_what(run)
        self.init_surcharge(event)

        # Add dynamic registration questions based on event configuration and requirements
        # Creates custom form fields for event-specific data collection
        self.init_questions(event, reg_counts)

        # Setup friend referral system functionality for social registration features
        # Enables users to invite friends during registration process
        self.init_bring_friend()

        # Append additional help text to ticket selection field for complete user guidance
        # Combines base help text with dynamic availability information
        self.fields["ticket"].help_text += ticket_help

    def sel_ticket_map(self, ticket: Any) -> None:
        """Update question requirements based on selected ticket type.

        Args:
            ticket: Selected ticket instance

        """
        """
        Check if given the selected ticket, we need to not require questions reserved
        to other tickets.
        """

        if "reg_que_tickets" not in self.params["features"]:
            return

        for question in self.questions:
            k = "q" + str(question.id)
            if k not in self.fields:
                continue
            tm = [i for i in question.tickets_map if i is not None]
            if ticket not in tm:
                self.fields[k].required = False

    def init_additionals(self) -> None:
        """Initialize additional tickets field if feature is enabled."""
        # Skip if additional tickets feature is not enabled
        if "additional_tickets" not in self.params["features"]:
            return

        # Get max_length from additional_tickets question, default to 5
        max_tickets = 5
        try:
            additional_question = RegistrationQuestion.objects.filter(
                event=self.params["run"].event, typ=RegistrationQuestionType.ADDITIONAL
            ).first()
            if additional_question and additional_question.max_length > 0:
                max_tickets = additional_question.max_length
        except ObjectDoesNotExist:
            pass  # Use default value if query fails

        # Create choice field with ticket quantity options (0 to max_tickets)
        self.fields["additionals"] = forms.ChoiceField(
            required=False,
            choices=[(i, str(i)) for i in range(max_tickets + 1)],
        )

        # Set initial value from instance if available
        if self.instance:
            self.initial["additionals"] = self.instance.additionals

    def init_bring_friend(self) -> None:
        """Initialize bring-a-friend code field for discounts."""
        if "bring_friend" not in self.params["features"]:
            return

        if self.instance.pk and self.initial["modified"] > 0:
            return

        help_text_message = _(
            "Enter the 'bring a friend' code provided by a registered participant "
            "to receive a %(amount)d discount on your registration fee",
        )
        self.fields["bring_friend"] = forms.CharField(
            required=False,
            max_length=100,
            label=_("Code 'Bring a friend'"),
            help_text=help_text_message % {"amount": self.params.get("bring_friend_discount_from", 0)},
        )

    def init_questions(self, event: Event, reg_counts: dict[str, Any]) -> None:
        """Initialize registration questions and ticket mapping.

        Args:
            event: Event instance
            reg_counts: Registration count data

        """
        self.tickets_map = {}
        if self.waiting_check:
            return
        self._init_reg_question(self.instance, event)
        for q in self.questions:
            self.init_question(q, reg_counts)
        self.tickets_map = json.dumps(self.tickets_map)

    def init_question(self, question: Any, registration_counts: Any) -> None:
        """Initialize a single registration question field.

        Args:
            question: Registration question instance
            registration_counts: Registration count data

        """
        if question.skip(self.instance, self.params["features"]):
            return

        k = self._init_field(question, registration_counts=registration_counts, is_organizer=False)
        if not k:
            return

        if question.profile:
            self.profiles["id_" + k] = question.profile_thumb.url

        if question.section:
            self.sections["id_" + k] = question.section.name
            if question.section.description:
                self.section_descriptions[question.section.name] = question.section.description

        if "reg_que_tickets" in self.params["features"]:
            tm = [i for i in question.tickets_map if i is not None]
            if tm:
                self.tickets_map[k] = tm

    def init_surcharge(self, event: Event) -> None:
        """Initialize date-based surcharge field if applicable.

        Args:
            event: Event instance

        """
        # date surcharge
        surcharge = get_date_surcharge(self.instance, event)
        if surcharge == 0:
            return
        ch = [(0, f"{surcharge}{self.params['currency_symbol']}")]
        self.fields["surcharge"] = forms.ChoiceField(required=True, choices=ch)

    def init_pay_what(self, run: Run) -> None:
        """Initialize pay-what-you-want donation field for non-waiting runs.

        Args:
            run: The Run instance to check status for field initialization.

        """
        # Skip if pay-what-you-want feature is not enabled
        if "pay_what_you_want" not in self.params["features"]:
            return

        # Skip for waiting runs
        if "waiting" in run.status:
            return

        # Create the pay-what-you-want field with validation (0-1000 range)
        self.fields["pay_what"] = forms.IntegerField(min_value=0, max_value=1000, required=False)

        # Set initial value from existing instance or default to 0
        if self.instance.pk and self.instance.pay_what:
            self.initial["pay_what"] = int(self.instance.pay_what)
        else:
            self.initial["pay_what"] = 0

    def init_quotas(self, event: Event, run: Run) -> None:
        """Initialize payment quotas field based on event configuration.

        Creates quota choices from available RegistrationQuota objects for the event,
        considering time constraints and current instance state. Sets up the quotas
        form field with appropriate choices and widget configuration.

        Args:
            event: Event instance containing quota configurations.
            run: Run instance with status and end date information.

        """
        quota_choices = []

        # Check if quota feature is enabled and run is not in waiting status
        if "reg_quotas" in self.params["features"] and "waiting" not in run.status:
            # Define labels for different quota options (1-5 quotas)
            quota_labels = [
                _("Single payment"),
                _("Two quotas"),
                _("Three quotas"),
                _("Four quotas"),
                _("Five quotas"),
            ]

            # Calculate days difference between today and run end date
            days_until_run_end = get_time_diff_today(run.end)

            # Process each available quota option for the event
            for registration_quota in RegistrationQuota.objects.filter(event=event).order_by("quotas"):
                # Include quota if sufficient time remains or if it's the current instance quota
                if days_until_run_end > registration_quota.days_available or (
                    self.instance and registration_quota.quotas == self.instance.quotas
                ):
                    # Ensure quotas value is within valid range (1-5)
                    quota_index = int(registration_quota.quotas) - 1
                    if 0 <= quota_index < len(quota_labels):
                        label = quota_labels[quota_index]

                        # Add surcharge information to label if applicable
                        if registration_quota.surcharge > 0:
                            label += f" ({registration_quota.surcharge}€)"
                        quota_choices.append((registration_quota.quotas, label))

        # Set default quota option if no valid quotas were found
        if not quota_choices:
            quota_choices.append((1, _("Default")))

        # Create the quotas form field with available choices
        self.fields["quotas"] = forms.ChoiceField(required=True, choices=quota_choices)

        # Hide field if only one option available and set initial value
        if len(quota_choices) == 1:
            self.fields["quotas"].widget = forms.HiddenInput()
            self.initial["quotas"] = quota_choices[0][0]

        # Set initial value for existing instances with quota data
        if self.instance.pk and self.instance.quotas:
            self.initial["quotas"] = self.instance.quotas

    def init_ticket(self, event: Event, registration_counts: dict, run: Run) -> str:
        """Initialize ticket selection field with available options.

        Args:
            event: Event instance to get tickets for
            registration_counts: Dictionary containing registration count data
            run: Run instance associated with the event

        Returns:
            HTML string containing formatted ticket descriptions for help text

        """
        # Get available tickets based on event, registration counts and run
        available_tickets = self.get_available_tickets(event, registration_counts, run)

        # Build ticket choices and collect descriptions for help text
        ticket_choices = []
        ticket_help_html = ""

        # Process each available ticket to create form choices and help text
        for ticket in available_tickets:
            # Generate formatted ticket name with pricing information
            ticket_display_name = ticket.get_form_text(currency_symbol=self.params["currency_symbol"])
            ticket_choices.append((ticket.id, ticket_display_name))

            # Add ticket description to help text if available
            if ticket.description:
                ticket_help_html += f"<p><b>{ticket.name}</b>: {ticket.description}</p>"

        # Create the ticket selection field with available choices
        self.fields["ticket"] = forms.ChoiceField(required=True, choices=ticket_choices)

        # Set initial ticket value from existing instance or parameters
        if self.instance and self.instance.ticket:
            self.initial["ticket"] = self.instance.ticket.id
        elif self.params.get("ticket"):
            self.initial["ticket"] = self.params["ticket"]

        return ticket_help_html

    def has_ticket(self, ticket_tier: Any) -> Any:
        """Check if registration has ticket of specified tier.

        Args:
            ticket_tier: TicketTier to check

        Returns:
            bool: True if registration has ticket of given tier

        """
        return self.instance.pk and self.instance.ticket and self.instance.ticket.tier == ticket_tier

    def has_ticket_primary(self) -> Any:
        """Check if registration has a primary (non-waiting/filler) ticket.

        Returns:
            bool: True if registration has primary ticket

        """
        excluded_ticket_tiers = [TicketTier.WAITING, TicketTier.FILLER]
        return self.instance.pk and self.instance.ticket and self.instance.ticket.tier not in excluded_ticket_tiers

    def check_ticket_visibility(self, registration_ticket: Any) -> bool:
        """Check if ticket should be visible to current user.

        Args:
            registration_ticket: RegistrationTicket instance

        Returns:
            bool: True if ticket should be visible

        """
        if registration_ticket.visible:
            return True

        if "ticket" in self.params and self.params["ticket"] == registration_ticket.id:
            return True

        return bool(self.instance.pk and self.instance.ticket == registration_ticket)

    def get_available_tickets(
        self,
        event: Event,
        registration_counts: dict,
        run: Run,
    ) -> list[RegistrationTicket] | list:
        """Get list of available tickets for registration.

        Returns tickets available for the current user based on their status,
        event configuration, and registration limits.

        Args:
            event: Event instance to get tickets for
            registration_counts: Dictionary containing registration count data by ticket type
            run: Run instance associated with the event

        Returns:
            List of RegistrationTicket objects available for registration,
            or empty list if no tickets are available

        """
        # Check if user has staff or NPC tickets - these take priority
        for tier in [TicketTier.STAFF, TicketTier.NPC]:
            # If the user is registered as a staff, show those options
            if self.has_ticket(tier):
                return RegistrationTicket.objects.filter(event=event, tier=tier).order_by("order")

        # Prevent new registrations if inscriptions are closed
        if not self.instance.pk and "closed" in run.status:
            return []

        # Build list of available player tickets
        available_tickets = []
        queried_tickets = RegistrationTicket.objects.filter(event=event).order_by("order")

        # Filter to giftable tickets only if this is a gift registration
        if self.gift:
            queried_tickets = queried_tickets.filter(giftable=True)

        # Evaluate each ticket for availability based on various constraints
        for ticket in queried_tickets:
            # Skip tickets not visible to current user
            if not self.check_ticket_visibility(ticket):
                continue

            # Skip tickets based on type restrictions
            if self.skip_ticket_type(event, run, ticket):
                continue

            # Skip tickets that have reached maximum capacity
            if self.skip_ticket_max(registration_counts, ticket):
                continue

            # Skip reduced-price tickets based on run configuration
            if self.skip_ticket_reduced(run, ticket):
                continue

            available_tickets.append(ticket)

        return available_tickets

    def skip_ticket_reduced(self, run: Run, ticket: RegistrationTicket) -> bool:
        """Check if reduced ticket should be skipped due to availability.

        Args:
            run: Run instance
            ticket: RegistrationTicket instance

        Returns:
            bool: True if ticket should be skipped

        """
        # if this reduced, check count
        if ticket.tier == TicketTier.REDUCED and (not self.instance or ticket != self.instance.ticket):
            ticket.available = get_reduced_available_count(run)
            if ticket.available <= 0:
                return True
        return False

    def skip_ticket_max(self, reg_counts: Any, ticket: Any) -> bool:
        """Check if ticket should be skipped due to maximum limit reached.

        Args:
            reg_counts: Registration count data
            ticket: RegistrationTicket instance

        Returns:
            bool: True if ticket should be skipped

        """
        # If the option has a maximum roof, check has not been reached
        if ticket.max_available > 0 and (not self.instance or ticket != self.instance.ticket):
            ticket.available = ticket.max_available
            key = f"tk_{ticket.id}"
            if key in reg_counts:
                ticket.available -= reg_counts[key]
            if ticket.available <= 0:
                return True
        return False

    def skip_ticket_type(self, event: Event, run: Run, ticket: RegistrationTicket) -> bool:  # noqa: C901 - Complex ticket eligibility logic
        """Determine if a ticket type should be skipped for the current member.

        This method checks various conditions to determine whether a specific ticket
        type should be hidden from the registration form for the current member.

        Args:
            event: Event instance containing the registration
            run: Run instance for the specific event occurrence
            ticket: RegistrationTicket instance to evaluate for visibility

        Returns:
            True if the ticket should be skipped (hidden), False if it should be shown

        Note:
            The logic considers ticket selection state, player history, run status,
            and member's existing registrations to determine ticket visibility.

        """
        # If this ticket is already selected in current registration flow, don't skip it
        if "ticket" in self.params and self.params["ticket"] == ticket.id:
            return False

        result = False

        # Hide new player tickets if member has previous non-waiting/staff/npc registrations
        if ticket.tier == TicketTier.NEW_PLAYER:
            past_regs = Registration.objects.filter(cancellation_date__isnull=True)
            past_regs = past_regs.exclude(ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC])
            past_regs = past_regs.filter(member=self.params["member"]).exclude(run=run)
            if past_regs.exists():
                result = True

        # Show waiting tickets only if run allows waiting or member already has waiting ticket
        elif ticket.tier == TicketTier.WAITING:
            if "waiting" not in run.status and not self.has_ticket(TicketTier.WAITING):
                result = True

        # Handle filler ticket visibility based on event config and member status
        elif ticket.tier == TicketTier.FILLER:
            filler_alway = get_event_config(event.id, "filler_always", default_value=False, context=self.params)
            if filler_alway:
                # With filler_always enabled, show only if run supports filler/primary or member has filler ticket
                if (
                    "filler" not in run.status
                    and "primary" not in run.status
                    and not self.has_ticket(TicketTier.FILLER)
                ):
                    result = True
            # Without filler_always, show only if run supports filler or member has filler ticket
            elif "filler" not in run.status and not self.has_ticket(TicketTier.FILLER):
                result = True

        # Show primary tickets only if run supports primary registration or member has primary ticket
        elif "primary" not in run.status and not self.has_ticket_primary():
            result = True

        return result

    def clean(self) -> dict:
        """Validate form data and check for valid friend codes."""
        # Get cleaned data from parent class
        form_data = super().clean()
        run = self.params["run"]

        # Check if bring_friend feature is enabled and field exists in form data
        if "bring_friend" in self.params["features"] and "bring_friend" in form_data:
            cod = form_data["bring_friend"]

            # Validate friend code if provided
            if cod:
                try:
                    # Look for registration with matching special code in same event
                    Registration.objects.get(special_cod=cod, run__event=run.event)
                except Registration.DoesNotExist:
                    # Add error if friend code not found
                    self.add_error("bring_friend", "I'm sorry, this friend code was not found")

        return form_data


class RegistrationGiftForm(RegistrationForm):
    """Form for RegistrationGift."""

    gift = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and filter fields based on giftable questions."""
        super().__init__(*args, **kwargs)

        # Build list of fields to keep: base fields plus giftable questions
        keep = ["run", "ticket"]
        keep.extend(["q" + str(q.id) for q in self.questions if q.giftable])

        # Remove fields not in keep list and update mandatory tracking
        list_del = [s for s in self.fields if s not in keep]
        for field in list_del:
            del self.fields[field]
            key = f"id_{field}"
            if key in self.mandatory:
                self.mandatory.remove(key)

        self.has_mandatory = len(self.mandatory) > 0


class OrgaRegistrationForm(BaseRegistrationForm):
    """Form for OrgaRegistration."""

    page_info = _("Manage event signups")

    page_title = _("Registrations")

    load_templates: ClassVar[list] = ["share"]

    load_js: ClassVar[list] = ["characters-reg-choices"]

    class Meta:
        model = Registration

        exclude = (
            "search",
            "modified",
            "refunded",
            "cancellation_date",
            "surcharge",
            "characters",
            "num_payments",
            "alert",
            "deadline",
            "redeem_code",
            "tot_payed",
            "tot_iscr",
            "quota",
            "payment_date",
        )

        widgets: ClassVar[dict] = {"member": AssociationMemberS2Widget}

    def get_automatic_field(self) -> set[str]:
        """Get automatic field names, excluding 'run' from parent's set."""
        # Get automatic fields from parent class
        automatic_fields = super().get_automatic_field()

        # Remove 'run' field (determined during initialization)
        automatic_fields.remove("run")

        return automatic_fields

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize registration form with run and event specific configuration.

        Args:
            *args: Variable length argument list passed to parent form.
            **kwargs: Arbitrary keyword arguments passed to parent form.

        """
        super().__init__(*args, **kwargs)

        # Extract run and event from params
        self.run = self.params["run"]
        self.event = self.params["run"].event

        # Configure member widget with association
        self.fields["member"].widget.set_association_id(self.params["association_id"])

        self.allow_run_choice()

        # Define form sections for field organization
        reg_section = _("Registration")
        char_section = _("Character")
        add_section = _("Details")
        main_section = _("Main")

        # Assign registration fields to registration section
        self.sections["id_member"] = reg_section
        self.sections["id_run"] = reg_section

        # Initialize registration-related fields
        self.init_quotas(reg_section)

        self.init_ticket(reg_section)

        self.init_additionals(reg_section)

        self.init_pay_what(reg_section)

        # Initialize character fields if feature is enabled
        if "character" in self.params["features"]:
            self.init_character(char_section)

        # Handle unique code field based on feature flag
        if "unique_code" in self.params["features"]:
            self.sections["id_special_cod"] = add_section
            self.reorder_field("special_cod")
        else:
            self.delete_field("special_cod")

        # Initialize organization-specific fields and clean up unused ones
        keys = self.init_orga_fields(main_section)
        all_fields = set(self.fields.keys()) - {field.replace("id_", "") for field in self.sections}
        for lbl in all_fields - set(keys):
            self.delete_field(lbl)

        # Control section visibility based on feature flag
        if "reg_que_sections" not in self.params["features"]:
            self.show_sections = True

    def init_additionals(self, registration_section: Any) -> None:
        """Initialize additional tickets section if feature is enabled."""
        # Check if additional tickets feature is available
        if "additional_tickets" not in self.params["features"]:
            return

        # Get max_length from additional_tickets question, default to 5
        max_tickets = 5
        try:
            additional_question = RegistrationQuestion.objects.filter(
                event=self.params["run"].event, typ=RegistrationQuestionType.ADDITIONAL
            ).first()
            if additional_question and additional_question.max_length > 0:
                max_tickets = additional_question.max_length
        except ObjectDoesNotExist:
            pass  # Use default value if query fails

        # Update field choices if the field exists
        if "additionals" in self.fields:
            self.fields["additionals"].widget.choices = [(i, str(i)) for i in range(max_tickets + 1)]

        # Register the additional tickets section
        self.sections["id_additionals"] = registration_section

    def init_pay_what(self, registration_section: int) -> None:
        """Initialize pay-what-you-want donation field configuration."""
        # Skip initialization if pay-what-you-want feature is not enabled
        if "pay_what_you_want" not in self.params["features"]:
            # Remove field from form to prevent NULL constraint violations
            self.delete_field("pay_what")
            return

        # Register section and configure field label/help text from event config
        self.sections["id_pay_what"] = registration_section

        # Ensure field is not required and has proper initial value
        self.fields["pay_what"].required = False
        if not self.initial.get("pay_what"):
            self.initial["pay_what"] = 0

        self.fields["pay_what"].label = get_event_config(
            self.params["run"].event_id,
            "pay_what_you_want_label",
            default_value=_("Free donation"),
            context=self.params,
        )
        self.fields["pay_what"].help_text = get_event_config(
            self.params["run"].event_id,
            "pay_what_you_want_descr",
            default_value=_("Freely indicate the amount of your donation"),
            context=self.params,
        )

    def init_ticket(self, registration_section: Any) -> None:
        """Initialize ticket field choices and set default if only one ticket available."""
        # Fetch and format ticket choices ordered by price (highest first)
        ticket_choices = [
            (ticket.id, ticket.get_form_text(currency_symbol=self.params["currency_symbol"]))
            for ticket in RegistrationTicket.objects.filter(event=self.params["run"].event).order_by("-price")
        ]
        self.fields["ticket"].choices = ticket_choices

        # Hide ticket selection and set default if only one option exists
        if len(ticket_choices) == 1:
            self.fields["ticket"].widget = forms.HiddenInput()
            self.initial["ticket"] = ticket_choices[0][0]

        self.sections["id_ticket"] = registration_section

    def init_quotas(self, registration_section: int) -> None:
        """Initialize quota selection field for payment installments.

        Args:
            registration_section: Section identifier for form organization.

        """
        # Skip if quota feature is not enabled
        if "reg_quotas" not in self.params["features"]:
            return

        # Define available payment installment options
        quota_choices = [(1, "Pagamento unico"), (2, "Due quote"), (3, "Tre quote")]

        # Create and configure quota choice field
        self.fields["quotas"] = forms.ChoiceField(
            required=True,
            choices=quota_choices,
            label=_("Quotas"),
            help_text=_("The number of payments to split the fee"),
        )

        # Set initial value and section assignment
        self.initial["quotas"] = self.instance.quotas
        self.sections["id_quotas"] = registration_section

    def init_character(self, char_section: Any) -> None:  # noqa: C901 - Complex character field initialization with feature-dependent logic
        """Initialize character selection fields in registration forms.

        Manages character assignment options based on event configuration
        and user permissions for character-based events.
        """
        # CHARACTER AND QUESTS
        if "orga_characters" not in self.params or not self.params["orga_characters"]:
            return

        mine = set()
        if self.instance.pk:
            self.initial["characters_new"] = self.get_init_multi_character()
            mine.update(list(self.initial["characters_new"]))
        taken_characters = set(
            RegistrationCharacterRel.objects.filter(reg__run_id=self.params["run"].id).values_list(
                "character_id",
                flat=True,
            ),
        )
        taken_characters = taken_characters - mine
        self.fields["characters_new"] = forms.ModelMultipleChoiceField(
            label=_("Characters"),
            queryset=self.params["run"].event.get_elements(Character).exclude(pk__in=taken_characters),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains", "number__icontains"]),
            required=False,
        )
        self.sections["id_characters_new"] = char_section

        if "questbuilder" in self.params["features"]:
            already = []
            assigned = []
            char = None
            char_ids = self.get_init_multi_character()
            if char_ids:
                char = Character.objects.get(pk=char_ids[0])
            for tnum, trait in self.params["traits"].items():
                if char and char.number == trait["char"]:
                    assigned.append(tnum)
                    continue
                already.append(tnum)
            available = Trait.objects.filter(event=self.event).exclude(number__in=already)
            for qtnum, qt in self.params["quest_types"].items():
                qt_id = f"qt_{qt['number']}"
                key = "id_" + qt_id
                self.sections[key] = char_section
                choices = [("0", _("--- NOT ASSIGNED ---"))]
                for q in self.params["quests"].values():
                    if q["typ"] != qtnum:
                        continue
                    for t in available:
                        if t.quest_id != q["id"]:
                            continue
                        choices.append((t.id, f"Q{q['number']} {q['name']} - {t}"))
                        if t.number in assigned:
                            self.initial[qt_id] = t.id

                self.fields[qt_id] = forms.ChoiceField(required=True, choices=choices, label=qt["name"])

    def clean_member(self) -> Any:
        """Validate member field to prevent duplicate registrations.

        Returns:
            Member: Validated member instance

        Raises:
            ValidationError: If member already has an active registration for the event

        """
        data = self.cleaned_data["member"]

        if "request" in self.params:
            post = self.params["request"].POST
            if "delete" in post and post["delete"] == "1":
                return data

        for reg in Registration.objects.filter(
            member=data,
            run=self.params["run"],
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
        ):
            if reg.pk != self.instance.pk:
                msg = "User already has a registration for this event!"
                raise ValidationError(msg)

        return data

    def clean_pay_what(self) -> Any:
        """Ensure pay_what has a valid integer value, defaulting to 0 if None or empty.

        Returns:
            int: Validated pay_what value (0 if None or empty)

        """
        data = self.cleaned_data.get("pay_what")
        # Convert None or empty string to 0 to prevent NULL constraint violations
        return data if data is not None else 0

    def get_init_multi_character(self) -> list[int]:
        """Get initial character IDs for multi-character registration."""
        character_registrations = RegistrationCharacterRel.objects.filter(reg__id=self.instance.pk)
        return character_registrations.values_list("character_id", flat=True)

    def _save_multi(self, field: str, instance: Registration) -> None:
        """Save multi-character relationships for registration.

        Args:
            field: Field name being saved
            instance: Registration instance

        """
        if field != "characters_new":
            return super()._save_multi(field, instance)

        # Get current and new character sets
        old = set(self.get_init_multi_character())
        new = set(self.cleaned_data["characters_new"].values_list("pk", flat=True))

        # Remove characters no longer selected
        for ch in old - new:
            RegistrationCharacterRel.objects.filter(character_id=ch, reg_id=instance.pk).delete()

        # Add newly selected characters
        for ch in new - old:
            RegistrationCharacterRel.objects.create(character_id=ch, reg_id=instance.pk)
        return None

    def clean_characters_new(self) -> Any:
        """Validate that new character assignments don't conflict with existing registrations.

        Returns:
            QuerySet: Cleaned character data if validation passes

        Raises:
            ValidationError: If character is already assigned to another player for this event

        """
        data = self.cleaned_data["characters_new"]
        character_ids = list(data.values_list("pk", flat=True))

        # Batch fetch all assigned characters
        assigned_qs = RegistrationCharacterRel.objects.filter(
            character_id__in=character_ids,
            reg__run=self.params["run"],
            reg__cancellation_date__isnull=True,
        ).select_related("character", "reg__member")

        if self.instance.pk:
            assigned_qs = assigned_qs.exclude(reg__id=self.instance.pk)

        # Create dict of assigned characters for fast lookup
        assigned_chars = {rel.character_id: rel for rel in assigned_qs}

        # Check each character against batch-fetched assignments
        for ch_id in character_ids:
            if ch_id in assigned_chars:
                rel = assigned_chars[ch_id]
                msg = f"Character '{rel.character}' already assigned to the player '{rel.reg.member}' for this event!"
                raise ValidationError(msg)

        return data


class RegistrationCharacterRelForm(MyForm):
    """Form for RegistrationCharacterRel."""

    class Meta:
        model = RegistrationCharacterRel
        exclude = ("reg", "character")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic field configuration based on event settings.

        Removes custom character fields that are disabled in event config and sets
        default custom_name from character instance if not already provided.
        """
        super().__init__(*args, **kwargs)

        # List of fields to delete, starting with profile
        dl = ["profile"]

        # Check event config for each custom character field and mark for deletion if disabled
        dl.extend(
            [
                s
                for s in ["name", "pronoun", "song", "public", "private"]
                if not get_event_config(
                    self.params["event"].id, "custom_character_" + s, default_value=False, context=self.params
                )
            ]
        )

        # Set default custom_name from character if not already in initial data
        if "custom_name" not in self.initial or not self.initial["custom_name"]:
            self.initial["custom_name"] = self.instance.character.name

        # Remove all fields marked for deletion
        for m in dl:
            self.delete_field("custom_" + m)


class OrgaRegistrationTicketForm(MyForm):
    """Form for OrgaRegistrationTicket."""

    page_info = _("Manage ticket types for participant registration")

    page_title = _("Tickets")

    class Meta:
        model = RegistrationTicket
        fields = "__all__"
        exclude = ("number", "order")
        widgets: ClassVar[dict] = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with tier choices and conditional field removal based on features."""
        super().__init__(*args, **kwargs)

        # Configure tier field based on available tiers for the event
        tiers = self.get_tier_available(self.params["run"].event, self.params)
        if len(tiers) > 1:
            self.fields["tier"].choices = tiers
        else:
            del self.fields["tier"]

        # Remove casting priority field if casting feature is disabled
        if "casting" not in self.params["features"]:
            self.delete_field("casting_priority")

        # Remove giftable field if gift feature is disabled
        if "gift" not in self.params["features"]:
            self.delete_field("giftable")

    @staticmethod
    def get_tier_available(event: Event, context: dict) -> list[tuple[str, str]]:
        """Get available ticket tiers based on event features and configuration.

        Filters ticket tiers by checking if required features are enabled for the event
        and if necessary configuration options are set. Returns only tiers that meet
        all requirements.

        Args:
            event: Event instance to check tier availability for. Must have
                  get_config method and id attribute.
            context: Dict with context information

        Returns:
            List of available ticket tier tuples in format (value, label).
            Each tuple represents a selectable ticket tier option.

        Example:
            >>> tiers = get_tier_available(my_event)
            >>> print(tiers)
            [('standard', 'Standard'), ('reduced', 'Reduced Price')]

        """
        available_tiers = []

        # Map ticket tiers to their required feature flags
        ticket_features = {
            TicketTier.LOTTERY: "lottery",
            TicketTier.WAITING: "waiting",
            TicketTier.FILLER: "filler",
            TicketTier.PATRON: "reduced",
            TicketTier.REDUCED: "reduced",
            TicketTier.NEW_PLAYER: "new_player",
        }

        # Map ticket tiers to their required configuration keys
        ticket_configs = {
            TicketTier.STAFF: "staff",
            TicketTier.NPC: "npc",
            TicketTier.COLLABORATOR: "collaborator",
            TicketTier.SELLER: "seller",
        }

        # Get enabled features for this event
        event_features = get_event_features(event.id)

        # Iterate through all possible ticket tier choices
        for tier_choice in TicketTier.choices:
            (tier_value, _tier_label) = tier_choice

            # Skip ticket tiers that require features not enabled for this event
            if tier_value in ticket_features and ticket_features[tier_value] not in event_features:
                continue

            # Skip ticket tiers that require configuration options not set
            if tier_value in ticket_configs and not get_event_config(
                event.id, f"ticket_{ticket_configs[tier_value]}", default_value=False, context=context
            ):
                continue

            # Add tier to available options if all checks pass
            available_tiers.append(tier_choice)

        return available_tiers


class OrgaRegistrationSectionForm(MyForm):
    """Form for OrgaRegistrationSection."""

    page_info = _("Manage signup form sections")

    page_title = _("Form section")

    class Meta:
        model = RegistrationSection
        exclude: ClassVar[list] = ["order"]


class OrgaRegistrationQuestionForm(MyForm):
    """Form for OrgaRegistrationQuestion."""

    page_info = _("Manage signup form questions")

    page_title = _("Form element")

    class Meta:
        model = RegistrationQuestion
        exclude: ClassVar[list] = ["order"]

        widgets: ClassVar[dict] = {
            "factions": FactionS2WidgetMulti,
            "tickets": TicketS2WidgetMulti,
            "allowed": AllowedS2WidgetMulti,
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize RegistrationQuestionForm with event-specific question configuration.

        Args:
            *args: Variable length argument list passed to parent form
            **kwargs: Arbitrary keyword arguments passed to parent form

        """
        super().__init__(*args, **kwargs)

        self.fields["factions"].widget.set_event(self.params["event"])

        self._init_type()

        if "reg_que_sections" not in self.params["features"]:
            self.delete_field("section")
        else:
            ch = [(m.id, str(m)) for m in RegistrationSection.objects.filter(event=self.params["run"].event)]
            ch.insert(0, ("", _("--- Empty")))
            self.fields["section"].choices = ch

        if "reg_que_allowed" not in self.params["features"]:
            self.delete_field("allowed")
        else:
            self.fields["allowed"].widget.set_event(self.params["event"])

        if "reg_que_tickets" not in self.params["features"]:
            self.delete_field("tickets")
        else:
            self.fields["tickets"].widget.set_event(self.params["event"])

        if "reg_que_faction" not in self.params["features"]:
            self.delete_field("factions")
        else:
            self.fields["factions"].choices = [
                (m.id, str(m)) for m in self.params["run"].event.get_elements(Faction).order_by("number")
            ]

        if "gift" not in self.params["features"]:
            self.delete_field("giftable")

        # Set status help
        visible_choices = {v for v, _ in self.fields["status"].choices}

        help_texts = {
            QuestionStatus.OPTIONAL: "The question is shown, and can be filled by the player",
            QuestionStatus.MANDATORY: "The question needs to be filled by the player",
            QuestionStatus.DISABLED: "The question is shown, but cannot be changed by the player",
            QuestionStatus.HIDDEN: "The question is not shown to the player",
        }

        self.fields["status"].help_text = ", ".join(
            f"<b>{choice.label}</b>: {text}" for choice, text in help_texts.items() if choice.value in visible_choices
        )

    def _init_type(self) -> None:
        """Initialize registration question type field choices.

        Filters question types based on existing usage and prevents duplicates.
        """
        # Add type of registration question to the available types
        registration_questions = self.params["event"].get_elements(RegistrationQuestion)
        already_used_types = list(registration_questions.values_list("typ", flat=True).distinct())

        if self.instance.pk and self.instance.typ:
            already_used_types.remove(self.instance.typ)
            # prevent cancellation if one of the default types
            self.prevent_canc = len(self.instance.typ) > 1

        available_choices = []
        for choice in RegistrationQuestionType.choices:
            # if it is related to a feature
            if len(choice[0]) > 1:
                # check it is not already present
                if choice[0] in already_used_types:
                    continue

                # check the feature is active
                if choice[0] not in ["ticket"] and choice[0] not in self.params["features"]:
                    continue

            available_choices.append(choice)
        self.fields["typ"].choices = available_choices


class OrgaRegistrationOptionForm(MyForm):
    """Form for OrgaRegistrationOption."""

    page_info = _("Manage signup form question options")

    page_title = _("Form Options")

    class Meta:
        model = RegistrationOption
        exclude: ClassVar[list] = ["order"]
        widgets: ClassVar[dict] = {"question": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and set question field from params if provided."""
        super().__init__(*args, **kwargs)

        # Set initial question value from params if question_id is present
        if "question_id" in self.params:
            self.initial["question"] = self.params["question_id"]


class OrgaRegistrationQuotaForm(MyForm):
    """Form for OrgaRegistrationQuota."""

    page_info = _("Manage dynamic payment installments for participants")

    page_title = _("Dynamic rates")

    class Meta:
        model = RegistrationQuota
        exclude = ("number",)

    def clean_quotas(self) -> int:
        """Validate that the number is unique for quotas of this event."""
        quotas = self.cleaned_data.get("quotas")
        event = self.cleaned_data.get("event") or (self.instance.event if self.instance.pk else None)

        if not event or not quotas:
            return quotas

        # Check if another quota with this number already exists for this event
        existing_quota = RegistrationQuota.objects.filter(event=event, quotas=quotas)

        # Exclude current instance if we're editing
        if self.instance.pk:
            existing_quota = existing_quota.exclude(pk=self.instance.pk)

        if existing_quota.exists():
            msg = _("A quota with %(quotas)d payments already exists for this event") % {"quotas": quotas}
            raise ValidationError(msg)

        return quotas


class OrgaRegistrationInstallmentForm(MyForm):
    """Form for OrgaRegistrationInstallment."""

    page_info = _("Manage fixed payment installments for participants")

    page_title = _("Fixed instalments")

    class Meta:
        model = RegistrationInstallment
        exclude = ("number",)

        widgets: ClassVar[dict] = {
            "date_deadline": DatePickerInput,
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure event-specific ticket widget."""
        super().__init__(*args, **kwargs)
        self.fields["tickets"].widget.set_event(self.params["event"])

    def clean_order(self) -> int:
        """Validate that the order is unique for installments of this event.

        Note: This validation only checks the order field. The complete validation
        that checks for common tickets is done in the clean() method after tickets
        are available in cleaned_data.
        """
        order = self.cleaned_data.get("order")
        if order is None:
            return order

        return order

    def clean(self) -> dict[str, any]:
        """Validate that only one deadline type (date or days) is specified and tickets are selected."""
        cleaned_data = super().clean()

        # Check if both deadline types are specified
        date_deadline = cleaned_data.get("date_deadline")
        days_deadline = cleaned_data.get("days_deadline")
        if days_deadline and date_deadline:
            self.add_error(
                "days_deadline",
                "Choose only one deadline for this installment, either by date or number of days!",
            )

        # Check if tickets are selected (tickets is a QuerySet from the form)
        tickets = cleaned_data.get("tickets")
        if not tickets or (hasattr(tickets, "count") and tickets.count() == 0):
            self.add_error(
                "tickets",
                _("You must select at least one ticket for this installment"),
            )
            # If no tickets, we can't check for conflicts, so return early
            return cleaned_data

        # Check for duplicate order with common tickets
        order = cleaned_data.get("order")
        event = cleaned_data.get("event") or (self.instance.event if self.instance.pk else None)

        if event and order is not None and tickets:
            # Get all installments with the same order for this event
            existing_installments = RegistrationInstallment.objects.filter(event=event, order=order).prefetch_related(
                "tickets"
            )

            # Exclude current instance if we're editing
            if self.instance.pk:
                existing_installments = existing_installments.exclude(pk=self.instance.pk)

            # Get the IDs of tickets we're trying to assign
            ticket_ids = set(tickets.values_list("id", flat=True))

            # Check each existing installment for common tickets
            for existing in existing_installments:
                existing_ticket_ids = set(existing.tickets.values_list("id", flat=True))
                common_tickets = ticket_ids & existing_ticket_ids

                if common_tickets:
                    # Get the names of common tickets for error message
                    common_ticket_objs = RegistrationTicket.objects.filter(id__in=common_tickets)
                    ticket_names = ", ".join([t.name for t in common_ticket_objs])

                    self.add_error(
                        "order",
                        _(
                            "An installment with order %(order)d already exists with the following common ticket(s): %(tickets)s"
                        )
                        % {"order": order, "tickets": ticket_names},
                    )
                    break  # Only report the first conflict found

        return cleaned_data


class OrgaRegistrationSurchargeForm(MyForm):
    """Form for OrgaRegistrationSurcharge."""

    page_info = _("Manage registration surcharges")

    page_title = _("Surcharge")

    class Meta:
        model = RegistrationSurcharge
        exclude = ("number",)

        widgets: ClassVar[dict] = {"date": DatePickerInput}


class PreRegistrationForm(forms.Form):
    """Form for PreRegistration."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize PreRegistrationForm with context-based field configuration.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments including 'context' context data

        """
        super().__init__()
        self.context = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        self.pre_reg = 1 + len(self.context["already"])

        cho = [("", "----")] + [(c.id, c.name) for c in self.context["choices"]]
        self.fields["new_event"] = forms.ChoiceField(
            required=False,
            choices=cho,
            label=_("Event"),
            help_text=_("Select the event you wish to pre-register for"),
        )

        existing = [al.pref for al in self.context["already"]]
        max_existing = max(existing) if existing else 1
        prefs = [r for r in range(1, max_existing + 4) if r not in existing]
        cho_pref = [(r, r) for r in prefs]

        # Check if preference editing is disabled via config
        if self.context.get("event") and get_association_config(
            self.context["event"].association_id,
            "pre_reg_preferences",
            default_value=False,
            context=self.context,
        ):
            self.fields["new_pref"] = forms.ChoiceField(
                required=False,
                choices=cho_pref,
                label=_("Preference"),
                help_text=_("Enter the order of preference of your pre-registration (1 is the maximum)"),
            )
            self.initial["new_pref"] = min(prefs)
        else:
            self.fields["new_pref"] = forms.CharField(widget=forms.HiddenInput(), initial=min(prefs))

        self.fields["new_info"] = forms.CharField(
            required=False,
            max_length=255,
            label=_("Informations"),
            help_text=_("Is there anything else you would like to tell us") + "?",
        )
