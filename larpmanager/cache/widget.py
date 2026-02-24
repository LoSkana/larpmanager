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

from datetime import timedelta
from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.db.models import Count, Max, Subquery
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext as _

from larpmanager.accounting.balance import (
    association_accounting_summary,
    get_run_accounting,
)
from larpmanager.cache.registration import get_registration_counts
from larpmanager.models.accounting import (
    AccountingItemExpense,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.casting import Casting, Quest, QuestType
from larpmanager.models.event import DevelopStatus, Event, RegistrationStatus, Run
from larpmanager.models.experience import AbilityTypePx, DeliveryPx
from larpmanager.models.form import BaseQuestionType, RegistrationQuestion, WritingQuestion
from larpmanager.models.member import LogOperationType, Membership, MembershipStatus
from larpmanager.models.miscellanea import HelpQuestion, Log
from larpmanager.models.registration import (
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationTicket,
)
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.core.common import format_datetime, get_coming_runs, get_event_features
from larpmanager.utils.users.deadlines import check_run_deadlines
from larpmanager.utils.users.registration import registration_available


def _compute_registration_status_code(run: Run) -> tuple[str, Any]:
    """Compute registration status code for a run.

    Returns:
        tuple: (status_code, additional_value)
    """
    features = get_event_features(run.event_id)
    status = run.registration_status

    # Handle simple status mappings
    simple_status_map = {
        RegistrationStatus.EXTERNAL: ("external", run.register_link),
        RegistrationStatus.PRE: ("preregister", None),
        RegistrationStatus.CLOSED: ("closed", None),
    }
    if status in simple_status_map:
        return simple_status_map[status]

    # Handle future status with opening time check
    if status == RegistrationStatus.FUTURE:
        if not run.registration_open:
            return "not_set", None
        current_datetime = timezone.now()
        if run.registration_open and run.registration_open > current_datetime:
            return "future", run.registration_open

    # Check registration availability for OPEN or FUTURE with past opening time
    run_status = {}
    registration_available(run, features, run_status)

    for status_type in ["primary", "filler", "waiting"]:
        if status_type in run_status:
            return status_type, run_status.get("count")

    return "closed", None


def _compute_registration_status(run: Run) -> str:
    """Compute human-readable registration status for a run.

    Returns:
        str: Localized status message
    """
    status_code, opening_datetime = _compute_registration_status_code(run)

    status_messages = {
        "external": _("Registrations on external link"),
        "preregister": _("Pre-registration active"),
        "not_set": _("Registrations opening not set"),
        "primary": _("Registrations open"),
        "filler": _("Filler registrations"),
        "waiting": _("Waiting list registrations"),
        "closed": _("Registration closed"),
    }

    if status_code == "future":
        if opening_datetime:
            formatted_opening_date = opening_datetime.strftime(format_datetime)
            return _("Registrations opening at: %(date)s") % {"date": formatted_opening_date}
        return _("Registrations opening not set")

    return status_messages.get(status_code, _("Registration closed"))


def _compute_registration_counts(run: Run) -> dict:
    """Compute registration counts: total, per-ticket and per-tier breakdown."""
    counts = get_registration_counts(run)

    total = counts.get("count_reg", 0)
    if not total:
        return {}

    tier_labels = [
        ("count_player", _("Player")),
        ("count_wait", _("Waiting")),
        ("count_staff", _("Staff")),
        ("count_fill", _("Filler")),
        ("count_seller", _("Seller")),
        ("count_lottery", _("Lottery")),
        ("count_npc", _("NPC")),
        ("count_collaborator", _("Collaborator")),
    ]

    active_tiers = [(label, counts[key]) for key, label in tier_labels if counts.get(key)]

    result = {_("Tot"): total}
    if len(active_tiers) > 1:
        result |= dict(active_tiers)

    return result


def _init_deadline_widget_cache(run: Run) -> dict:
    """Compute deadline data for widget cache."""
    deadline_results = check_run_deadlines([run])
    if not deadline_results:
        return {}

    deadline_data = deadline_results[0]

    # Extract the counts
    counts = {}
    for category in ["pay", "pay_del", "casting", "memb", "memb_del", "fee", "fee_del", "profile", "profile_del"]:
        if category in deadline_data:
            counts[category] = len(deadline_data[category])

    return counts


def _init_user_character_widget_cache(run: Run) -> dict:
    """Compute character counts by status for widget cache."""
    # Count characters for each status
    counts = {}

    # Get all characters for this run
    characters = run.event.get_elements(Character)

    # Count by status
    counts["creation"] = characters.filter(status=CharacterStatus.CREATION).count()
    counts["proposed"] = characters.filter(status=CharacterStatus.PROPOSED).count()
    counts["review"] = characters.filter(status=CharacterStatus.REVIEW).count()
    counts["approved"] = characters.filter(status=CharacterStatus.APPROVED).count()

    return counts


def _init_casting_widget_cache(run: Run) -> dict:
    """Compute casting statistics for widget cache."""
    counts = {}

    # Get all characters for this run
    characters = run.event.get_elements(Character)
    all_character_ids = set(characters.values_list("id", flat=True))

    # Precompute list of assigned character IDs via RegistrationCharacterRel
    assigned_character_ids = set(
        RegistrationCharacterRel.objects.filter(registration__run=run).values_list("character_id", flat=True)
    )

    # Count assigned and unassigned characters
    counts["assigned"] = len(assigned_character_ids)
    counts["unassigned"] = len(all_character_ids - assigned_character_ids)

    # Get members with active casting preferences but no assigned character
    members_with_casting = set(
        Casting.objects.filter(run=run, active=True).values_list("member_id", flat=True).distinct()
    )

    # Get members who already have a character assigned in this run
    members_with_character = set(
        RegistrationCharacterRel.objects.filter(registration__run=run)
        .values_list("registration__member_id", flat=True)
        .distinct()
    )

    # Players waiting = those with preferences but no assigned character
    waiting_members = members_with_casting - members_with_character
    counts["waiting"] = len(waiting_members)

    return counts


def _init_orga_accounting_widget_cache(run: Run) -> dict:
    """Compute accounting statistics for widget cache."""
    summary, _accounting_data = get_run_accounting(run, {})
    return summary


def _init_exe_accounting_widget_cache(association_id: int) -> dict:
    """Compute association accounting statistics for widget cache (current year)."""
    context = {"association_id": association_id}

    # Get accounting data summary
    association_accounting_summary(context)
    data = {}
    for key in ["global_sum", "bank_sum"]:
        data[key] = context.get(key, 0)
    return data


def _init_exe_deadline_widget_cache(association_id: int) -> dict:
    """Compute association deadline statistics for widget cache (aggregates all upcoming runs)."""
    # Get all upcoming runs for the association
    runs = get_coming_runs(association_id, future=True)

    # Initialize aggregated counts
    total_counts = {}

    # Iterate through all runs and aggregate deadline counts
    for run in runs:
        run_counts = _init_deadline_widget_cache(run)
        for category, count in run_counts.items():
            total_counts[category] = total_counts.get(category, 0) + count

    return total_counts


def _init_orga_log_widget_cache(run: Run) -> dict:
    """Compute log statistics and recent logs for event dashboard."""
    base_query = Log.objects.filter(run_id=run.id)

    # Count logs by operation type
    operation_counts = {}
    for op_type, op_label in LogOperationType.choices:
        count = base_query.filter(operation_type=op_type).count()
        if count > 0:
            operation_counts[op_type] = {"label": op_label, "count": count}

    # Get recent logs (last 5)
    recent_logs = base_query.select_related("member").order_by("-created")[:5]

    return {"operation_counts": operation_counts, "recent_logs": list(recent_logs), "total_count": base_query.count()}


def _init_exe_log_widget_cache(association_id: int) -> dict:
    """Compute log statistics and recent logs for organization dashboard."""
    base_query = Log.objects.filter(association_id=association_id)

    # Count logs by operation type
    operation_counts = {}
    for op_type, op_label in LogOperationType.choices:
        count = base_query.filter(operation_type=op_type).count()
        if count > 0:
            operation_counts[op_type] = {"label": op_label, "count": count}

    # Get recent logs (last 5)
    recent_logs = base_query.select_related("member", "run__event").order_by("-created")[:5]

    return {"operation_counts": operation_counts, "recent_logs": list(recent_logs), "total_count": base_query.count()}


def _init_exe_actions_cache(association_id: int) -> dict:
    """Compute all action counts for executive dashboard."""
    data = {}

    # Ongoing runs (in START or SHOW status) - save all data needed by template
    ongoing_runs = (
        Run.objects.filter(
            event__association_id=association_id,
            development__in=[DevelopStatus.START, DevelopStatus.SHOW],
        )
        .select_related("event", "event__parent")
        .order_by("end")
    )

    ongoing_runs_data = []
    for run in ongoing_runs:
        run_data = {
            "slug": run.get_slug,
            "name": str(run),
            "pretty_dates": run.pretty_dates,
            "parent": str(run.event.parent) if run.event.parent else None,
            "development_display": run.get_development_display(),
            "registration_status": _compute_registration_status(run),
            "registration_counts": _compute_registration_counts(run),
        }
        ongoing_runs_data.append(run_data)

    data["ongoing_runs"] = ongoing_runs_data

    # Past runs to conclude
    runs_to_conclude = Run.objects.filter(
        event__association_id=association_id,
        development__in=[DevelopStatus.START, DevelopStatus.SHOW],
        end__lt=timezone.now().date(),
    )
    count = runs_to_conclude.count()
    if count > 0:
        data["past_runs"] = {"count": count, "runs": list(runs_to_conclude.values_list("search", flat=True))}

    # Pending expenses
    pending_expenses_count = AccountingItemExpense.objects.filter(
        run__event__association_id=association_id,
        is_approved=False,
    ).count()
    if pending_expenses_count > 0:
        data["pending_expenses"] = {"count": pending_expenses_count}

    # Pending invoice approvals split by type
    for typ, key in [
        (PaymentType.REGISTRATION, "pending_invoices_registration"),
        (PaymentType.DONATE, "pending_invoices_donation"),
        (PaymentType.COLLECTION, "pending_invoices_collection"),
        (PaymentType.MEMBERSHIP, "pending_invoices_membership"),
    ]:
        count = PaymentInvoice.objects.filter(
            association_id=association_id,
            status=PaymentStatus.SUBMITTED,
            typ=typ,
        ).count()
        if count > 0:
            data[key] = {"count": count}

    # Pending refunds
    pending_refunds_count = RefundRequest.objects.filter(
        association_id=association_id,
        status=RefundStatus.REQUEST,
    ).count()
    if pending_refunds_count > 0:
        data["pending_refunds"] = {"count": pending_refunds_count}

    # Pending members
    pending_members_count = Membership.objects.filter(
        association_id=association_id,
        status=MembershipStatus.SUBMITTED,
    ).count()
    if pending_members_count > 0:
        data["pending_members"] = {"count": pending_members_count}

    # Open help questions (last 90 days, most recent per member, user-originated and not closed)
    base_queryset = HelpQuestion.objects.filter(
        association_id=association_id, created__gte=timezone.now() - timedelta(days=90)
    )
    latest_created_per_member = (
        base_queryset.values("member_id").annotate(latest_created=Max("created")).values("latest_created")
    )
    open_questions_count = base_queryset.filter(
        created__in=Subquery(latest_created_per_member), is_user=True, closed=False
    ).count()
    if open_questions_count > 0:
        data["open_help_questions"] = {"count": open_questions_count}

    return data


def _init_orga_actions_cache(run: Run) -> dict:
    """Compute all action counts for event organizer dashboard."""
    data = {}

    # Pending expenses (for orga level)
    pending_expenses_count = AccountingItemExpense.objects.filter(run=run, is_approved=False).count()
    if pending_expenses_count > 0:
        data["pending_expenses"] = {"count": pending_expenses_count}

    # Pending registration invoice approvals
    pending_payments_count = PaymentInvoice.objects.filter(
        registration__run=run,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    ).count()
    if pending_payments_count > 0:
        data["pending_invoices_registration"] = {"count": pending_payments_count}

    # Registration questions without options
    registration_questions_without_options = list(
        run.event.get_elements(RegistrationQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if registration_questions_without_options:
        data["registration_questions_incomplete"] = {
            "count": len(registration_questions_without_options),
            "names": [q.name for q in registration_questions_without_options],
        }

    # Writing questions without options
    writing_questions_without_options = list(
        run.event.get_elements(WritingQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if writing_questions_without_options:
        data["writing_questions_incomplete"] = {
            "count": len(writing_questions_without_options),
            "names": [q.name for q in writing_questions_without_options],
        }

    # Installments with both deadlines
    installments_with_both_deadlines = run.event.get_elements(RegistrationInstallment).filter(
        date_deadline__isnull=False, days_deadline__isnull=False
    )
    if installments_with_both_deadlines.exists():
        data["installments_both_deadlines"] = {
            "count": installments_with_both_deadlines.count(),
            "names": [str(i) for i in installments_with_both_deadlines],
        }

    # Tickets missing final installment
    tickets_missing_final_installment = run.event.get_elements(RegistrationTicket).exclude(installments__amount=0)
    if tickets_missing_final_installment.exists():
        data["tickets_missing_final_installment"] = {
            "count": tickets_missing_final_installment.count(),
            "names": [t.name for t in tickets_missing_final_installment],
        }

    _init_orga_actions_writing(data, run)

    # Registration quotas existence check
    data["has_registration_quotas"] = run.event.get_elements(RegistrationQuota).exists()

    # Registration installments existence check
    data["has_registration_installments"] = run.event.get_elements(RegistrationInstallment).exists()

    # Open help questions (last 90 days, most recent per member, user-originated and not closed)
    base_queryset = HelpQuestion.objects.filter(
        association_id=run.event.association_id, run=run, created__gte=timezone.now() - timedelta(days=90)
    )
    latest_created_per_member = (
        base_queryset.values("member_id").annotate(latest_created=Max("created")).values("latest_created")
    )
    open_questions_count = base_queryset.filter(
        created__in=Subquery(latest_created_per_member), is_user=True, closed=False
    ).count()
    if open_questions_count > 0:
        data["open_help_questions"] = {"count": open_questions_count}

    return data


def _init_orga_actions_writing(data: dict, run: Run) -> None:
    """Compute writing action counts for event organizer dashboard."""
    # Character existence check
    data["has_characters"] = run.event.get_elements(Character).exists()

    # Pending character approvals
    proposed_characters_count = run.event.get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if proposed_characters_count > 0:
        data["proposed_characters"] = {"count": proposed_characters_count}

    # Quest types existence check
    data["has_quest_types"] = run.event.get_elements(QuestType).exists()

    # Quest types without quests
    unused_quest_types = list(
        run.event.get_elements(QuestType).annotate(quest_count=Count("quests")).filter(quest_count=0)
    )
    if unused_quest_types:
        data["quest_types_without_quests"] = {
            "count": len(unused_quest_types),
            "names": [qt.name for qt in unused_quest_types],
        }

    # Quests without traits
    unused_quests = list(run.event.get_elements(Quest).annotate(trait_count=Count("traits")).filter(trait_count=0))
    if unused_quests:
        data["quests_without_traits"] = {"count": len(unused_quests), "names": [q.name for q in unused_quests]}

    # Ability types existence check
    data["has_ability_types"] = run.event.get_elements(AbilityTypePx).exists()

    # Ability types without abilities
    ability_types_without_abilities = list(
        run.event.get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    if ability_types_without_abilities:
        data["ability_types_without_abilities"] = {
            "count": len(ability_types_without_abilities),
            "names": [at.name for at in ability_types_without_abilities],
        }

    # Delivery PX existence check
    data["has_delivery_px"] = run.event.get_elements(DeliveryPx).exists()


# Widget list for run-level widgets
orga_widget_list = {
    "actions": _init_orga_actions_cache,
    "deadlines": _init_deadline_widget_cache,
    "user_character": _init_user_character_widget_cache,
    "casting": _init_casting_widget_cache,
    "accounting": _init_orga_accounting_widget_cache,
    "logs": _init_orga_log_widget_cache,
}

# Widget list for association-level widgets
exe_widget_list = {
    "actions": _init_exe_actions_cache,
    "accounting": _init_exe_accounting_widget_cache,
    "deadlines": _init_exe_deadline_widget_cache,
    "logs": _init_exe_log_widget_cache,
}


def get_widget_cache_key(entity_type: str, entity_id: int, widget_name: str) -> str:
    """Generate cache key for widget data."""
    return f"widget_cache_{entity_type}_{entity_id}_{widget_name}"


def get_widget_cache(
    entity: Run | int, entity_type: str, entity_id: int, widget_list: dict, widget_name: str = ""
) -> dict:
    """Get widget data from cache or compute if not cached.

    Args:
        entity: Object on which to recover widget (either Run, or
        entity_type: Type of entity ('run' or 'association')
        entity_id: ID of the entity
        widget_list: List of available widgets
        widget_name: Name of the widget to retrieve

    Returns:
        dict: Widget data

    Raises:
        Http404: If widget is not found
    """
    cached_data_function = widget_list.get(widget_name)
    if not cached_data_function:
        msg = f"widget {widget_name} not found in widget list"
        raise Http404(msg)

    cache_key = get_widget_cache_key(entity_type, entity_id, widget_name)
    cached_data = cache.get(cache_key)

    # If not in cache, update and get fresh data
    if cached_data is None:
        cached_data = cached_data_function(entity)
        # Cache the result with 1-day timeout
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_data


def get_orga_widget_cache(run: Run, widget_name: str) -> dict:
    """Get deadline widget data from cache or compute if not cached."""
    return get_widget_cache(run, "run", run.id, orga_widget_list, widget_name)


def get_exe_widget_cache(association_id: int, widget_name: str) -> dict:
    """Get deadline widget data from cache or compute if not cached."""
    return get_widget_cache(association_id, "association", association_id, exe_widget_list, widget_name)


def clear_widget_cache(run_id: int) -> None:
    """Clear cached widget data for a run."""
    for widget_name in orga_widget_list:
        cache_key = get_widget_cache_key("run", run_id, widget_name)
        cache.delete(cache_key)


def clear_widget_cache_association(association_id: int) -> None:
    """Clear cached widget data for an association."""
    for widget_name in exe_widget_list:
        cache_key = get_widget_cache_key("association", association_id, widget_name)
        cache.delete(cache_key)


def clear_widget_cache_for_runs(run_ids: list[int]) -> None:
    """Clear widget cache for multiple runs."""
    for run_id in run_ids:
        clear_widget_cache(run_id)


def clear_widget_cache_for_event(event_id: int) -> None:
    """Clear widget cache for all runs in an event."""
    run_ids = Run.objects.filter(event_id=event_id).values_list("id", flat=True)
    clear_widget_cache_for_runs(list(run_ids))


def clear_widget_cache_for_association(association_id: int) -> None:
    """Clear widget cache for all runs in an association and association-level widgets."""
    # Clear run-level widgets
    event_ids = Event.objects.filter(association_id=association_id).values_list("id", flat=True)
    run_ids = Run.objects.filter(event_id__in=event_ids).values_list("id", flat=True)
    clear_widget_cache_for_runs(list(run_ids))

    # Clear association-level widgets
    clear_widget_cache_association(association_id)


def reset_widgets(instance: Any) -> None:
    """Reset widget cache data for related elements."""
    if hasattr(instance, "run") and instance.run:
        clear_widget_cache(instance.run.id)
        clear_widget_cache_association(instance.run.event.association_id)
    elif hasattr(instance, "event") and instance.event:
        clear_widget_cache_for_event(instance.event.id)
        clear_widget_cache_association(instance.event.association_id)
    elif hasattr(instance, "association_id") and instance.association_id:
        clear_widget_cache_association(instance.association_id)
