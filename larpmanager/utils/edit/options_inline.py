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
"""Inline (no-modal, no-iframe) editing of question options.

Generic handlers shared by the registration form (RegistrationOption) and the
writing form (WritingOption). All endpoints are AJAX-only and return JSON, so
the option list can be edited in place inside the question edit page.
"""

from typing import Any

from django.forms.models import model_to_dict
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.character import OrgaWritingOptionForm
from larpmanager.forms.registration import OrgaRegistrationOptionForm
from larpmanager.models.form import (
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.member import LogOperationType
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import get_element
from larpmanager.utils.edit.backend import save_log


def _inline_models(permission: str) -> tuple[type, type, type]:
    """Return (question_model, option_model, form_class) for the given permission."""
    if permission == "orga_character_form":
        return WritingQuestion, WritingOption, OrgaWritingOptionForm
    return RegistrationQuestion, RegistrationOption, OrgaRegistrationOptionForm


def inline_options_config(context: dict, permission: str) -> dict[str, Any]:
    """Build the column / feature configuration for the inline options editor.

    Args:
        context: Event context (must contain "features" and "event")
        permission: Permission type, switches registration vs writing

    Returns:
        Dict with visibility flags and M2M choices used by the template.
    """
    features = context.get("features", {})

    if permission == "orga_character_form":
        cfg = {
            "show_price": False,
            "show_max": "wri_que_max" in features,
            "show_requirements": "wri_que_requirements" in features,
            "show_tickets": "wri_que_tickets" in features,
        }
        if cfg["show_requirements"]:
            cfg["requirements_choices"] = (
                WritingOption.objects.filter(event=context["event"])
                .select_related("question")
                .order_by("question__order", "order")
            )
        if cfg["show_tickets"]:
            from larpmanager.models.registration import RegistrationTicket  # noqa: PLC0415

            cfg["tickets_choices"] = context["event"].get_elements(RegistrationTicket).order_by("order")
    else:
        cfg = {
            "show_price": True,
            "show_max": True,
            "show_requirements": False,
            "show_tickets": False,
        }

    # Secondary (expandable) row is needed when there is more than the name to edit
    cfg["has_details"] = True
    return cfg


def _serialize_option(option: Any, *, show_price: bool) -> dict[str, Any]:
    """Serialize an option to the JSON payload consumed by the inline editor."""
    data = {
        "uuid": str(option.uuid),
        "name": option.name,
        "description": option.description,
        "max_available": option.max_available,
    }
    if show_price:
        data["price"] = f"{option.price:.2f}"

    # M2M fields are present only on WritingOption
    for m2m in ("requirements", "tickets"):
        if hasattr(option, m2m):
            data[m2m] = list(getattr(option, m2m).values_list("id", flat=True))

    return data


def _merge_partial_data(request: HttpRequest, option_model: type, instance: Any | None) -> dict[str, Any]:
    """Merge POSTed fields over current instance values (PATCH semantics).

    Only fields present in the POST are overridden; everything else keeps the
    instance value (or the model default for new options), so a single-field
    autosave does not wipe other fields.
    """
    base = instance if instance is not None and instance.pk else option_model()
    data: dict[str, Any] = model_to_dict(base)

    m2m_fields = ("requirements", "tickets")
    for key in request.POST:
        if key in ("csrfmiddlewaretoken", "question_uuid") or key.startswith("__present_"):
            continue
        values = request.POST.getlist(key)
        data[key] = values if key in m2m_fields else values[0]

    # An empty multiselect submits nothing: the client sends "__present_<field>"
    # so we can tell "cleared" apart from "untouched"
    for field in m2m_fields:
        if f"__present_{field}" in request.POST and field not in request.POST:
            data[field] = []

    return data


def options_inline_save(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    option_uuid: str | None = None,
    writing_type: str | None = None,
) -> JsonResponse:
    """Create or partially update an option from the inline editor.

    For new options the question UUID must be passed as ``question_uuid`` in
    the POST body. Returns the serialized option on success, or a field ->
    errors mapping on validation failure.
    """
    context = check_event_context(request, event_slug, permission)

    if request.method != "POST":
        return JsonResponse({"success": False, "errors": {"__all__": [str(_("Invalid request"))]}}, status=405)

    question_model, option_model, form_class = _inline_models(permission)

    if writing_type:
        # Local import to avoid a circular dependency with utils.edit.orga
        from larpmanager.utils.edit.orga import check_writing_form_type  # noqa: PLC0415

        check_writing_form_type(context, writing_type)

    # Resolve instance and parent question
    instance = None
    if option_uuid:
        get_element(context, option_uuid, "el", option_model)
        instance = context["el"]
        context["question"] = instance.question
    else:
        question_uuid = request.POST.get("question_uuid")
        if not question_uuid:
            return JsonResponse(
                {"success": False, "errors": {"__all__": [str(_("Missing question"))]}},
                status=400,
            )
        get_element(context, question_uuid, "question", question_model)

    # Mirror the context keys that backend_edit provides to BaseModelForm
    context["elementTyp"] = option_model
    context["request"] = request

    data = _merge_partial_data(request, option_model, instance)
    form = form_class(data, instance=instance, context=context)

    if not form.is_valid():
        errors = {field: [str(e) for e in errs] for field, errs in form.errors.items()}
        return JsonResponse({"success": False, "errors": errors}, status=400)

    saved = form.save()
    save_log(context, option_model, saved, element_uuid=option_uuid)

    cfg = inline_options_config(context, permission)
    return JsonResponse({"success": True, "option": _serialize_option(saved, show_price=cfg["show_price"])})


def options_inline_reorder(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    writing_type: str | None = None,
) -> JsonResponse:
    """Persist a full ordering of a question's options in a single request.

    Expects ``uuids`` in the POST body as a list of option UUIDs in the
    desired order. All options must belong to the same question of the event.
    """
    context = check_event_context(request, event_slug, permission)

    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    if writing_type:
        from larpmanager.utils.edit.orga import check_writing_form_type  # noqa: PLC0415

        check_writing_form_type(context, writing_type)

    _question_model, option_model, _form_class = _inline_models(permission)

    uuids = request.POST.getlist("uuids[]") or request.POST.getlist("uuids")
    if not uuids:
        return JsonResponse({"success": False}, status=400)

    options = list(option_model.objects.filter(event=context["event"], uuid__in=uuids))
    by_uuid = {str(opt.uuid): opt for opt in options}

    # All options must exist and belong to a single question
    if len(by_uuid) != len(uuids) or len({opt.question_id for opt in options}) > 1:
        return JsonResponse({"success": False}, status=400)

    for idx, opt_uuid in enumerate(uuids, start=1):
        by_uuid[opt_uuid].order = idx
    option_model.objects.bulk_update(options, ["order"])

    return JsonResponse({"success": True})


def options_inline_delete(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    option_uuid: str,
    writing_type: str | None = None,
) -> JsonResponse:
    """Delete an option from the inline editor, returning JSON."""
    context = check_event_context(request, event_slug, permission)

    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    if writing_type:
        from larpmanager.utils.edit.orga import check_writing_form_type  # noqa: PLC0415

        check_writing_form_type(context, writing_type)

    _question_model, option_model, _form_class = _inline_models(permission)

    get_element(context, option_uuid, "el", option_model)
    element = context["el"]

    save_log(context, option_model, element, operation_type=LogOperationType.DELETE)
    element.delete()

    return JsonResponse({"success": True})
