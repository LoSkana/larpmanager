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
"""Global suppression list of email addresses that must not be contacted."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.db import transaction

from larpmanager.models.miscellanea import EmailSuppression, SuppressionReason

logger = logging.getLogger(__name__)

# Transient bounces only suppress after this many consecutive failures
SOFT_BOUNCE_LIMIT = 5

# Reasons that block delivery as soon as a single event is received
HARD_REASONS = {SuppressionReason.BOUNCE_PERMANENT, SuppressionReason.COMPLAINT, SuppressionReason.MANUAL}

SUPPRESSION_CACHE_TIMEOUT = 3600


def _cache_key(email: str) -> str:
    """Return the cache key holding the suppression flag of an address."""
    return f"email_suppressed_{email.strip().lower()}"


def get_suppression_state(email: str) -> dict[str, Any] | None:
    """Return the cached suppression state of an address, or None when it is clean."""
    if not email:
        return None
    key = _cache_key(email)
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    state = (
        EmailSuppression.objects.filter(email=email.strip().lower()).values("reason", "active", "bounce_count").first()
    )
    cache.set(key, state or 0, SUPPRESSION_CACHE_TIMEOUT)
    return state


def is_suppressed(email: str, *, bulk: bool = True) -> bool:
    """Check whether an address is currently blocked from receiving emails.

    Bulk communications are blocked by any active suppression. Transactional
    mails (password resets, receipts, confirmations) are only blocked by a
    permanent bounce: a spam complaint or a temporarily full mailbox must not
    lock a member out of their own account.
    """
    state = get_suppression_state(email)
    if not state or not state["active"]:
        return False
    if bulk:
        return True
    return state["reason"] == SuppressionReason.BOUNCE_PERMANENT


def get_suppressed_emails(emails: list[str], *, bulk: bool = True) -> set[str]:
    """Return the lowercased addresses of a list that are currently blocked.

    Resolves the whole list with a single query, so a broadcast does not hit
    the database once per recipient.
    """
    cleaned = {email.strip().lower() for email in emails if email and email.strip()}
    if not cleaned:
        return set()

    # Addresses are always normalised to lowercase before being stored, so the plain
    # lookup can use the unique index instead of scanning the whole table
    rows = EmailSuppression.objects.filter(email__in=cleaned, active=True).values_list("email", "reason")
    if bulk:
        return {email.lower() for email, _reason in rows}
    return {email.lower() for email, reason in rows if reason == SuppressionReason.BOUNCE_PERMANENT}


def clear_soft_bounces(email: str) -> None:
    """Reset the transient bounce counter of an address after a successful delivery.

    Without this a handful of temporary failures spread over months would
    eventually add up to a permanent block.
    """
    email = (email or "").strip().lower()
    state = get_suppression_state(email)
    if not state or state["active"] or not state["bounce_count"]:
        return

    # The same row lock used by suppress_email: without it a bounce processed concurrently
    # would read the old counter and write it back, losing the reset
    with transaction.atomic():
        obj = EmailSuppression.all_objects.select_for_update().filter(email=email).first()
        if not obj or obj.active or not obj.bounce_count:
            return
        obj.bounce_count = 0
        obj.save(update_fields=["bounce_count", "updated", "last_event"])

    reset_suppression_cache(email)


def reset_suppression_cache(email: str) -> None:
    """Drop the cached suppression flag of an address."""
    cache.delete(_cache_key(email))


def suppress_email(email: str, reason: str, raw: dict[str, Any] | None = None) -> EmailSuppression | None:
    """Record a bounce or complaint, activating suppression when warranted.

    Transient bounces accumulate and only block once SOFT_BOUNCE_LIMIT is reached,
    while permanent bounces, complaints and manual entries block immediately.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None

    # SES fans out events for the same address concurrently, so the row is locked while
    # it is updated: soft deleted rows still hold the unique email and are revived here
    with transaction.atomic():
        obj, _created = EmailSuppression.all_objects.get_or_create(
            email=email,
            defaults={"reason": reason, "bounce_count": 0, "active": False},
        )
        obj = EmailSuppression.all_objects.select_for_update().get(pk=obj.pk)
        if obj.deleted:
            obj.deleted = None
            obj.deleted_by_cascade = False

        obj.bounce_count += 1
        # A hard reason is never downgraded by a later transient bounce, unless the address
        # was released: keeping it would let the next soft limit revive a permanent block
        if not obj.active or obj.reason not in HARD_REASONS:
            obj.reason = reason
        obj.raw = raw
        # Suppression is only ever raised here: releasing an address is up to unsuppress_email
        obj.active = obj.active or reason in HARD_REASONS or obj.bounce_count >= SOFT_BOUNCE_LIMIT
        obj.save()

    reset_suppression_cache(email)
    logger.info("Suppression recorded: reason=%s active=%s count=%s", reason, obj.active, obj.bounce_count)
    return obj


def unsuppress_email(email: str) -> None:
    """Remove an address from the local suppression list and from the SES one."""
    email = (email or "").strip().lower()
    if not email:
        return

    EmailSuppression.objects.filter(email=email).update(active=False, bounce_count=0)
    reset_suppression_cache(email)
    _ses_delete_suppressed_destination(email)


@lru_cache(maxsize=1)
def _get_ses_client() -> Any | None:
    """Return the shared SES client, or None when the credentials are not configured.

    The client is built once: releasing a long list of addresses would otherwise
    pay the setup cost of a new client for every single one of them.
    """
    if not all(
        [
            getattr(conf_settings, "AWS_SES_ACCESS_KEY_ID", None),
            getattr(conf_settings, "AWS_SES_SECRET_ACCESS_KEY", None),
            getattr(conf_settings, "AWS_SES_REGION_NAME", None),
        ]
    ):
        return None

    return boto3.client(
        "sesv2",
        aws_access_key_id=conf_settings.AWS_SES_ACCESS_KEY_ID,
        aws_secret_access_key=conf_settings.AWS_SES_SECRET_ACCESS_KEY,
        region_name=conf_settings.AWS_SES_REGION_NAME,
    )


def _ses_delete_suppressed_destination(email: str) -> None:
    """Delete an address from the SES account level suppression list, if configured."""
    try:
        client = _get_ses_client()
        if not client:
            return
        client.delete_suppressed_destination(EmailAddress=email)
    except (ClientError, BotoCoreError) as exc:
        # A missing entry is expected whenever SES never suppressed the address
        logger.info("SES suppression delete skipped: %s", exc)
