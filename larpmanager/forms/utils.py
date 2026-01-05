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

from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.db.models import Q, QuerySet
from django.forms.widgets import Widget
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms
from tinymce.widgets import TinyMCE

from larpmanager.models.access import AssociationRole, EventRole, PermissionModule
from larpmanager.models.casting import Trait
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    Run,
)
from larpmanager.models.experience import AbilityPx, AbilityTemplatePx
from larpmanager.models.form import WritingOption
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.miscellanea import WarehouseArea, WarehouseContainer, WarehouseItem, WarehouseTag
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
)
from larpmanager.models.writing import (
    Character,
    Faction,
    FactionType,
    Plot,
)

if TYPE_CHECKING:
    from larpmanager.forms.base import BaseModelForm

# defer script loaded by form

css_delimeter = "/*@#§*/"


def render_js(cls: Any) -> list[str]:
    """Render JavaScript includes with defer attribute for forms.

    Args:
        cls: Media class containing JavaScript paths

    Returns:
        list: HTML script tags with defer attributes

    """
    return [format_html('<script defer src="{}"></script>', cls.absolute_path(path)) for path in cls._js]


forms.widgets.Media.render_js = render_js


# special widget


class ReadOnlyWidget(Widget):
    """Widget for displaying read-only form fields."""

    input_type = None
    template_name = "forms/widgets/read_only.html"


class DatePickerInput(forms.TextInput):
    """Date picker input widget for forms."""

    input_type = "date_p"


class DateTimePickerInput(forms.TextInput):
    """Date and time picker input widget for forms."""

    input_type = "datetime_p"


class TimePickerInput(forms.TextInput):
    """Time picker input widget for forms."""

    input_type = "time_p"


class SlugInput(forms.TextInput):
    """Slug input widget with special formatting."""

    input_type = "slug"
    template_name = "forms/widgets/slug.html"


class RoleCheckboxWidget(forms.CheckboxSelectMultiple):
    """Custom checkbox widget for role permission selection with help text."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize widget with feature help text and mapping.

        Args:
            *args: Variable positional arguments
            **kwargs: Arbitrary keyword arguments including help_text and feature_map

        """
        self.feature_help = kwargs.pop("help_text", {})
        self.feature_map = kwargs.pop("feature_map", {})
        super().__init__(*args, **kwargs)

    def render(
        self,
        name: str,
        value: list[str] | None,
        attrs: dict[str, str] | None = None,
        renderer: Any = None,  # noqa: ARG002
    ) -> str:
        """Render checkbox widget with tooltips and help links.

        Generates HTML for a checkbox widget where each option includes:
        - A checkbox input with proper ID and value
        - A label associated with the checkbox
        - A help icon that triggers tutorial functionality
        - Tooltip text with additional information

        Args:
            name: The form field name used for the checkbox group
            value: List of currently selected option values, or None if no selection
            attrs: Dictionary of HTML attributes to apply to the widget, may be None
            renderer: Form renderer instance (unused in this implementation)

        Returns:
            Safe HTML string containing the complete checkbox widget markup

        """
        # Ensure value is a list for membership checking
        value = value or []

        # Localized text for help icon tooltip
        know_more = _("click on the icon to open the tutorial")

        # Build list of checkbox elements as tuples for format_html_join
        checkbox_elements = []
        for i, (option_value, option_label) in enumerate(self.choices):
            # Create unique ID for each checkbox using index
            checkbox_id = f"{attrs.get('id', name)}_{i}"

            # Determine if this option should be checked
            checked = "checked" if option_value in value else ""

            # Get help text for this specific feature option
            help_text = self.feature_help.get(option_value, "")
            feature_value = self.feature_map.get(option_value, "")

            # Add tuple with all the data needed for this checkbox
            checkbox_elements.append(
                (
                    help_text,
                    know_more,
                    name,
                    option_value,
                    checkbox_id,
                    checked,
                    checkbox_id,
                    option_label,
                    feature_value,
                ),
            )

        # Use format_html_join to safely generate the HTML
        return format_html_join(
            "\n",
            '<div class="feature_checkbox lm_tooltip"><span class="hide lm_tooltiptext">{} ({})</span><input type="checkbox" name="{}" value="{}" id="{}" {}> <label for="{}">{}</label> <a href="#" feat="{}"><i class="fas fa-question-circle"></i></a></div>',
            checkbox_elements,
        )


class TranslatedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Model multiple choice field with translated labels."""

    def label_from_instance(self, obj: Any) -> str:
        """Get translated label for model instance.

        Args:
            obj: Model instance

        Returns:
            str: Translated name of the instance

        """
        return _(obj.name)


def prepare_permissions_role(form: BaseModelForm, typ: type) -> None:
    """Prepare permission fields for role forms based on enabled features.

    Creates dynamic form fields for permissions organized by modules,
    with checkboxes for available permissions based on enabled features.

    Args:
        form: Form instance to add permission fields to. Must have instance, params,
              fields, and modules attributes.
        typ: Permission model type (AssociationPermission or EventPermission class).
             Must have objects manager with filter, select_related methods.

    Returns:
        None: Modifies form in-place by adding permission fields and setting attributes.

    Side Effects:
        - Adds permission fields to form.fields dict
        - Sets form.modules list with field names
        - Sets form.prevent_canc=True for role number 1 (executives)

    """
    # Early return for executive role (number 1) - prevent cancellation
    if form.instance and form.instance.number == 1:
        form.prevent_canc = True
        return

    # Initialize modules list for storing field names
    form.modules = []

    # Extract enabled features from form parameters
    enabled_features = set(form.params.get("features", []))

    # Get currently selected permission IDs for existing instances
    selected_permission_ids = set()
    if getattr(form.instance, "pk", None):
        selected_permission_ids = set(form.instance.permissions.values_list("pk", flat=True))

    # Build base queryset for permissions - filter by enabled features and visibility
    base_queryset = (
        typ.objects.filter(hidden=False)
        .select_related("feature", "module")
        .filter(Q(feature__placeholder=True) | Q(feature__slug__in=enabled_features))
        .order_by("module__order", "number", "pk")
    )

    # Group permissions by module for organized display
    permissions_by_module = defaultdict(list)
    for permission in base_queryset:
        permissions_by_module[permission.module_id].append(permission)

    # Ensure modules attribute exists on form
    form.modules = getattr(form, "modules", [])

    # Create form fields for each module that has permissions
    for module in PermissionModule.objects.order_by("order"):
        module_permissions = permissions_by_module.get(module.id, [])
        if not module_permissions:
            continue

        # Generate unique field name for this module
        field_name = f"perm_{module.pk}"

        # Create module label with icon markup
        label = format_html("<i class='fa-solid fa-{}'></i> {}", module.icon, _(module.name))

        # Determine which permissions should be initially selected
        module_permission_ids = [permission.pk for permission in module_permissions]
        initial_values = [
            permission_id for permission_id in selected_permission_ids if permission_id in module_permission_ids
        ]

        # Create the multiple choice field with custom widget
        form.fields[field_name] = TranslatedModelMultipleChoiceField(
            required=False,
            queryset=typ.objects.filter(pk__in=module_permission_ids).order_by("number", "pk"),
            widget=RoleCheckboxWidget(
                help_text={permission.pk: permission.descr for permission in module_permissions},
                feature_map={permission.pk: permission.feature_id for permission in module_permissions},
            ),
            label=label,
            initial=initial_values,
        )

        # Track field name for template rendering
        form.modules.append(field_name)


def save_permissions_role(instance: EventRole | AssociationRole, form: BaseModelForm) -> None:
    """Save selected permissions for a role instance.

    Args:
        instance: Role instance to save permissions for
        form: Form containing selected permission data

    Side effects:
        Clears existing permissions and adds selected ones
        Skips permission saving for role number 1 (executives)

    """
    instance.save()
    if form.instance and form.instance.number == 1:
        return

    sel = []
    for el in form.modules:
        sel.extend([e.pk for e in form.cleaned_data[el]])

    instance.permissions.clear()
    instance.permissions.add(*sel)

    instance.save()


class EventS2Widget(s2forms.ModelSelect2Widget):
    """Represents EventS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def set_exclude(self, exclude_value: int) -> None:
        """Set the exclude flag."""
        self.excl = exclude_value

    def get_queryset(self) -> QuerySet[Event]:
        """Get non-template events for the association, optionally excluding a specific event."""
        # Filter non-template events for the association
        queryset = Event.objects.filter(association_id=self.association_id, template=False)

        # Exclude specific event if excl attribute is set
        if hasattr(self, "excl"):
            queryset = queryset.exclude(pk=self.excl)

        return queryset


class CampaignS2Widget(s2forms.ModelSelect2Widget):
    """Represents CampaignS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def label_from_instance(self, obj: object) -> str:
        """Return string representation of the given object."""
        return str(obj)

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def set_exclude(self, exclude: int) -> None:
        """Set the exclude flag."""
        self.exclude = exclude

    def get_queryset(self) -> QuerySet[Event]:
        """Return events excluding templates and child events."""
        # Filter for parent events only, excluding templates
        queryset = Event.objects.filter(parent_id__isnull=True, association_id=self.association_id, template=False)

        # Exclude specific event if specified
        if hasattr(self, "excl"):
            queryset = queryset.exclude(pk=self.exclude)

        return queryset


class TemplateS2Widget(s2forms.ModelSelect2Widget):
    """Represents TemplateS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[Event]:
        """Return queryset of template events for the association."""
        return Event.objects.filter(association_id=self.association_id, template=True)


class AssocMS2:
    """Represents AssocMS2 model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet:
        """Return members queryset for this association."""
        return get_members_queryset(self.association_id)

    @staticmethod
    def label_from_instance(obj: Member) -> str:
        """Return formatted label with member name and email."""
        return f"{obj.display_real()} - {obj.email}"


class AssociationMemberS2WidgetMulti(AssocMS2, s2forms.ModelSelect2MultipleWidget):
    """Represents AssociationMemberS2WidgetMulti model."""


class AssociationMemberS2Widget(AssocMS2, s2forms.ModelSelect2Widget):
    """Represents AssociationMemberS2Widget model."""


class RunMemberS2Widget(s2forms.ModelSelect2Widget):
    """Represents RunMemberS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and set allowed attribute to None."""
        super().__init__(*args, **kwargs)
        self.allowed_member_ids = None

    def set_run(self, run: Run) -> None:
        """Set allowed members for a run based on registrations and event roles."""
        # Get registered members for this run (non-cancelled)
        registration_queryset = Registration.objects.filter(run=run, cancellation_date__isnull=True)
        self.allowed_member_ids = set(registration_queryset.values_list("member_id", flat=True))

        # Add members with event roles
        event_role_queryset = EventRole.objects.filter(event_id=run.event_id).prefetch_related("members")
        self.allowed_member_ids.update(event_role_queryset.values_list("members__id", flat=True))

        # Set required attribute
        # noinspection PyUnresolvedReferences
        self.attrs["required"] = "required"

    def get_queryset(self) -> QuerySet[Member]:
        """Return members filtered by allowed IDs."""
        return Member.objects.filter(pk__in=self.allowed_member_ids)

    def label_from_instance(self, obj: Any) -> str:
        """Generate label combining object display name and email.

        Args:
            obj: Object with display_real() method and email attribute.

        Returns:
            Formatted string with display name and email.

        """
        # noinspection PyUnresolvedReferences
        return f"{obj.display_real()} - {obj.email}"


def get_association_people(association_id: int) -> list[tuple[int, str]]:
    """Get list of people associated with an association for form choices.

    Args:
        association_id: Association ID to get members for

    Returns:
        list: List of (member_id, display_string) tuples

    """
    que = Membership.objects.select_related("member").filter(association_id=association_id)
    que = que.exclude(status=MembershipStatus.EMPTY).exclude(status=MembershipStatus.REWOKED)
    return [(f.member_id, f"{f.member!s} - {f.member.email}") for f in que]


def get_run_choices(self: Any, *, past: bool = False) -> None:
    """Generate run choices for form fields.

    Args:
        self: Form instance with params containing association ID
        past: If True, filter to recent past runs only

    Side effects:
        Creates or updates 'run' field in form with run choices
        Sets initial value if run is in params

    """
    choices = [("", "-----")]
    runs = (
        Run.objects.filter(event__association_id=self.params["association_id"]).select_related("event").order_by("-end")
    )
    if past:
        reference_date = timezone.now() - timedelta(days=30)
        runs = runs.filter(end__gte=reference_date.date(), development__in=[DevelopStatus.SHOW, DevelopStatus.DONE])
    choices.extend([(run.uuid, str(run)) for run in runs])

    if "run" not in self.fields:
        self.fields["run"] = forms.ChoiceField(label=_("Session"))

    self.fields["run"].choices = choices
    if "run" in self.params:
        self.initial["run"] = self.params["run"].uuid


class EventRegS2Widget(s2forms.ModelSelect2Widget):
    """Represents EventRegS2Widget model."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[Registration]:
        """Return registrations for the current event with optimized prefetching."""
        return Registration.objects.prefetch_related("run", "run__event").filter(run__event=self.event)

    def label_from_instance(self, obj: Any) -> str:
        """Return formatted label for instance, appending cancellation marker if cancelled."""
        s = str(obj)
        # noinspection PyUnresolvedReferences
        if obj.cancellation_date:
            s += " - CANC"
        return s


class AssocRegS2Widget(s2forms.ModelSelect2Widget):
    """Represents AssocRegS2Widget model."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[Registration]:
        """Return registrations for the current association with optimized queries."""
        return Registration.objects.prefetch_related("run", "run__event").filter(
            run__event__association_id=self.association_id,
        )

    def label_from_instance(self, obj: Any) -> str:
        """Return label for form field instance, appending cancellation status if present."""
        s = str(obj)
        # Append cancellation indicator if object has been cancelled
        # noinspection PyUnresolvedReferences
        if obj.cancellation_date:
            s += " - CANC"
        return s


class RunS2Widget(s2forms.ModelSelect2Widget):
    """Represents RunS2Widget model."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[Run]:
        """Return runs for the current association."""
        return Run.objects.filter(event__association_id=self.association_id)


class RunRegS2Widget(s2forms.ModelSelect2Widget):
    """Select2 widget for registrations filtered by run."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_run(self, run: Run) -> None:
        """Set the run for this instance."""
        self.run = run

    def get_queryset(self) -> QuerySet[Registration]:
        """Return non-cancelled registrations for the current run."""
        return (
            Registration.objects.filter(run=self.run, cancellation_date__isnull=True)
            .select_related("member", "ticket")
            .order_by("member__name", "member__surname")
        )

    def label_from_instance(self, obj: Any) -> str:
        """Return formatted label for registration instance."""
        return str(obj)


class TransferTargetRunS2Widget(s2forms.ModelSelect2Widget):
    """Select2 widget for target runs in registration transfers."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the current event to exclude runs from the same event."""
        self.event = event

    def get_queryset(self) -> QuerySet[Run]:
        """Return runs from different events that are not concluded or cancelled."""
        return (
            Run.objects.filter(event__association_id=self.event.association_id)
            .exclude(event_id=self.event.id)
            .exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC])
            .select_related("event")
            .order_by("-start")
        )


class EventCharacterS2:
    """Represents EventCharacterS2 model."""

    search_fields: ClassVar[list] = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
        "title__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[Character]:
        """Return optimized queryset of event characters ordered by number."""
        return (
            self.event.get_elements(Character)
            .only("id", "name", "number", "teaser", "title", "event_id")
            .order_by("number")
        )


class EventCharacterS2WidgetMulti(EventCharacterS2, s2forms.ModelSelect2MultipleWidget):
    """Represents EventCharacterS2WidgetMulti model."""


class EventCharacterS2Widget(EventCharacterS2, s2forms.ModelSelect2Widget):
    """Represents EventCharacterS2Widget model."""


class RunCampaignS2:
    """Manages loading run from a campaign."""

    search_fields: ClassVar[list] = [
        "search__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event to look for other campaign events."""
        if event.parent_id:
            # Event is in a campaign - get parent and all siblings
            parent_event = Event.objects.get(id=event.parent_id)
            # Get all children of the parent (siblings) plus the parent itself
            event_ids = list(Event.objects.filter(parent_id=parent_event.id).values_list("id", flat=True))
            event_ids.append(parent_event.id)
        else:
            # Event is standalone or parent - get this event and all children
            event_ids = list(Event.objects.filter(parent_id=event.id).values_list("id", flat=True))
            event_ids.append(event.id)

        self.event_ids = event_ids

    def get_queryset(self) -> QuerySet[Character]:
        """Return queryset of runs of allowed event ids."""
        return Run.objects.filter(event_id__in=self.event_ids).order_by("-end")


class RunCampaignS2WidgetMulti(RunCampaignS2, s2forms.ModelSelect2MultipleWidget):
    """Represents RunCampaignS2WidgetMulti model."""


class RunCampaignS2Widget(RunCampaignS2, s2forms.ModelSelect2Widget):
    """Represents RunCampaignS2Widget model."""


class EventPlotS2:
    """Represents EventPlotS2 model."""

    search_fields: ClassVar[list] = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[Plot]:
        """Return queryset of Plot elements for this event."""
        return self.event.get_elements(Plot)


class EventPlotS2WidgetMulti(EventPlotS2, s2forms.ModelSelect2MultipleWidget):
    """Represents EventPlotS2WidgetMulti model."""


class EventPlotS2Widget(EventPlotS2, s2forms.ModelSelect2Widget):
    """Represents EventPlotS2Widget model."""


class EventTraitS2:
    """Represents EventTraitS2 model."""

    search_fields: ClassVar[list] = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[Trait]:
        """Return optimized queryset of traits for the event, ordered by number."""
        return self.event.get_elements(Trait).only("id", "name", "number", "teaser", "event_id").order_by("number")


class EventTraitS2WidgetMulti(EventTraitS2, s2forms.ModelSelect2MultipleWidget):
    """Represents EventTraitS2WidgetMulti model."""


class EventTraitS2Widget(EventTraitS2, s2forms.ModelSelect2Widget):
    """Represents EventTraitS2Widget model."""


class EventWritingOptionS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    """Represents EventWritingOptionS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "description__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[WritingOption]:
        """Return queryset of WritingOption elements for the event."""
        return self.event.get_elements(WritingOption)


class FactionS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    """Represents FactionS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[Faction]:
        """Return factions associated with this event."""
        return self.event.get_elements(Faction)

    def label_from_instance(self, instance: Faction) -> str:
        """Return faction label with type code suffix."""
        # Map faction types to their single-letter codes
        code = {FactionType.PRIM: "P", FactionType.TRASV: "T", FactionType.SECRET: "S"}
        return f"{instance.name} ({code[instance.typ]})"


class AbilityS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    """Represents AbilityS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[AbilityPx]:
        """Return ability experience entries for this event."""
        return self.event.get_elements(AbilityPx)


class AbilityTemplateS2WidgetMulti(s2forms.ModelSelect2Widget):
    """Represents AbilityTemplateS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[RegistrationTicket]:
        """Return registration tickets for the event."""
        return self.event.get_elements(AbilityTemplatePx)

    def label_from_instance(self, obj: Any) -> str:
        """Return string representation of the given object."""
        return obj.get_full_name()


class TicketS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    """Represents TicketS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event for this instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[RegistrationTicket]:
        """Return registration tickets for the event."""
        return self.event.get_elements(RegistrationTicket)


class AllowedS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    """Represents AllowedS2WidgetMulti model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event and compute allowed member IDs from event roles."""
        self.event = event
        # Query event roles with prefetched members
        que = EventRole.objects.filter(event_id=event.id).prefetch_related("members")
        # Extract flattened list of member IDs who have roles in this event
        self.allowed_member_ids = que.values_list("members__id", flat=True)

    def get_queryset(self) -> QuerySet[Member]:
        """Return queryset of members filtered by allowed IDs."""
        return Member.objects.filter(pk__in=self.allowed_member_ids)


class WarehouseContainerS2Widget(s2forms.ModelSelect2Widget):
    """Represents WarehouseContainerS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "description__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[WarehouseContainer]:
        """Return warehouse containers for the current association."""
        return WarehouseContainer.objects.filter(association_id=self.association_id)


class WarehouseAreaS2Widget(s2forms.ModelSelect2Widget):
    """Represents WarehouseAreaS2Widget model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "description__icontains",
    ]

    def set_event(self, event: Event) -> None:
        """Set the event instance."""
        self.event = event

    def get_queryset(self) -> QuerySet[WarehouseArea]:
        """Return warehouse areas for this event."""
        return self.event.get_elements(WarehouseArea)


class WarehouseItemS2(s2forms.ModelSelect2Widget):
    """Represents WarehouseItemS2 model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "description__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[WarehouseItem]:
        """Return warehouse items filtered by association."""
        return WarehouseItem.objects.filter(association_id=self.association_id)


class WarehouseItemS2WidgetMulti(WarehouseItemS2, s2forms.ModelSelect2MultipleWidget):
    """Represents WarehouseItemS2WidgetMulti model."""


class WarehouseItemS2Widget(WarehouseItemS2, s2forms.ModelSelect2Widget):
    """Represents WarehouseItemS2Widget model."""


class WarehouseTagS2(s2forms.ModelSelect2Widget):
    """Represents WarehouseTagS2 model."""

    search_fields: ClassVar[list] = [
        "name__icontains",
        "description__icontains",
    ]

    def set_association_id(self, association_id: int) -> None:
        """Set the association ID for this widget."""
        self.association_id = association_id

    def get_queryset(self) -> QuerySet[WarehouseTag]:
        """Return warehouse tags filtered by association."""
        return WarehouseTag.objects.filter(association_id=self.association_id)


class WarehouseTagS2WidgetMulti(WarehouseTagS2, s2forms.ModelSelect2MultipleWidget):
    """Represents WarehouseTagS2WidgetMulti model."""


class WarehouseTagS2Widget(WarehouseTagS2, s2forms.ModelSelect2Widget):
    """Represents WarehouseTagS2Widget model."""


def remove_choice(choices: list[tuple[str, str]], type_to_remove: str) -> list[tuple[str, str]]:
    """Remove a specific choice from a list of choices.

    Args:
        choices: List of (key, value) choice tuples
        type_to_remove: Choice key to remove

    Returns:
        list: New choice list without the specified type

    """
    filtered_choices = []
    for key, value in choices:
        if key == type_to_remove:
            continue
        filtered_choices.append((key, value))
    return filtered_choices


class RedirectForm(forms.Form):
    """Form for Redirect."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic slug choices from provided slugs parameter."""
        slugs = self.params = kwargs.pop("slugs")
        super().__init__(*args, **kwargs)

        # Build enumerated choices from slugs list
        cho = [(counter, el) for counter, el in enumerate(slugs)]

        # Add dynamic slug field with enumerated choices
        self.fields["slug"] = forms.ChoiceField(choices=cho, label="Element")


def get_members_queryset(association_id: int) -> QuerySet[Member]:
    """Get queryset of members for an association with accepted status.

    Args:
        association_id: Association ID to filter members for

    Returns:
        QuerySet: Members with accepted, submitted, or joined membership status

    """
    allowed_statuses = [MembershipStatus.ACCEPTED, MembershipStatus.SUBMITTED, MembershipStatus.JOINED]
    queryset = Member.objects.prefetch_related("memberships")
    return queryset.filter(memberships__association_id=association_id, memberships__status__in=allowed_statuses)


# CSRF-aware upload handler for TinyMCE
# This JavaScript function is injected into TinyMCE configuration to handle file uploads
# with proper CSRF token authentication
_TINYMCE_CSRF_UPLOAD_HANDLER = """function(blobInfo, progress) {
    return new Promise(function(resolve, reject) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload_media/');

        // Get CSRF token from cookie or form
        const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                         document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];

        if (csrftoken) {
            xhr.setRequestHeader('X-CSRFToken', csrftoken);
        }

        xhr.upload.onprogress = function(e) {
            progress(e.loaded / e.total * 100);
        };

        xhr.onload = function() {
            if (xhr.status === 403) {
                reject('HTTP Error: ' + xhr.status + ' - CSRF verification failed');
                return;
            }
            if (xhr.status < 200 || xhr.status >= 300) {
                reject('HTTP Error: ' + xhr.status);
                return;
            }

            const json = JSON.parse(xhr.responseText);
            if (!json || typeof json.location !== 'string') {
                reject('Invalid JSON: ' + xhr.responseText);
                return;
            }

            resolve(json.location);
        };

        xhr.onerror = function() {
            reject('Image upload failed due to a XHR Transport error. Code: ' + xhr.status);
        };

        const formData = new FormData();
        formData.append('file', blobInfo.blob(), blobInfo.filename());

        xhr.send(formData);
    });
}"""


class CSRFTinyMCE(TinyMCE):
    """TinyMCE widget with CSRF-aware image upload handler.

    This widget extends the standard TinyMCE widget to include proper CSRF token
    handling for file uploads, preventing 403 Forbidden errors.
    """

    def __init__(self, attrs=None, mce_attrs=None) -> None:  # noqa: ANN001
        """Initialize TinyMCE widget with CSRF-aware upload handler.

        Args:
            attrs: HTML attributes for the widget
            mce_attrs: TinyMCE-specific configuration attributes

        """
        # Merge custom upload handler with any existing mce_attrs
        mce_attrs = mce_attrs or {}
        mce_attrs["images_upload_handler"] = _TINYMCE_CSRF_UPLOAD_HANDLER

        super().__init__(attrs=attrs, mce_attrs=mce_attrs)


class WritingTinyMCE(CSRFTinyMCE):
    """TinyMCE widget with custom styling for character markers and CSRF upload support."""

    def __init__(self) -> None:
        """Initialize TinyMCE widget with custom styling and CSRF-aware upload handler."""
        mce_attrs = {
            "rows": 20,
            "content_style": ".char-marker { background: yellow !important; }",
        }
        super().__init__(attrs=mce_attrs)
