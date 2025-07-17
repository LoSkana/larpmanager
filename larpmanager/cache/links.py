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

from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.models.access import AssocRole, EventRole
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.registration import Registration
from larpmanager.utils.auth import is_lm_admin


def cache_event_links(request):
    ctx = {}
    if not request.user.is_authenticated or request.assoc["id"] == 0:
        return ctx

    ctx = cache.get(get_cache_event_key(request.user.id, request.assoc["id"]))
    if ctx:
        # print(ctx)
        return ctx

    ctx = {}
    ref = datetime.now() - timedelta(days=10)
    ref = ref.date()

    member = request.user.member

    # get future events
    que = Registration.objects.filter(member=member, run__end__gte=ref)
    que = que.filter(cancellation_date__isnull=True, run__event__assoc_id=request.assoc["id"])
    que = que.select_related("run", "run__event")
    ctx["reg_menu"] = [(r.run.event.slug, r.run.number, str(r.run)) for r in que]

    assoc_id = request.assoc["id"]

    # collect number and ids of assoc_roles
    ctx["assoc_role"] = {}
    for ar in member.assoc_roles.filter(assoc_id=assoc_id):
        ctx["assoc_role"][ar.number] = ar.id
    # if lm admin, put assoc role admin
    if is_lm_admin(request):
        ctx["assoc_role"][1] = 1

    # for each event, collect number and ids of event_roles
    ctx["event_role"] = {}
    for er in member.event_roles.filter(event__assoc_id=assoc_id).select_related("event"):
        if er.event.slug not in ctx["event_role"]:
            ctx["event_role"][er.event.slug] = {}
        ctx["event_role"][er.event.slug][er.number] = er.id

    # get all runs access
    ctx["all_runs"] = {}
    ctx["open_runs"] = {}
    all_runs = Run.objects.filter(event__assoc_id=assoc_id).select_related("event").order_by("end")
    admin = 1 in ctx["assoc_role"]
    for r in all_runs:
        if r.event.deleted:
            continue
        roles = None
        if admin:
            roles = [1]
        if r.event.slug in ctx["event_role"]:
            roles = list(ctx["event_role"][r.event.slug].keys())
        if not roles:
            continue
        ctx["all_runs"][r.id] = roles
        if r.development not in (DevelopStatus.DONE, DevelopStatus.CANC):
            ctx["open_runs"][r.id] = {
                "e": r.event.slug,
                "r": r.number,
                "s": str(r),
                "k": (r.start if r.start else datetime.max.date()),
            }

    ctx["topbar"] = ctx["event_role"] or ctx["assoc_role"]

    cache.set(get_cache_event_key(request.user.id, request.assoc["id"]), ctx, 60)
    return ctx


def reset_run_event_links(event):
    for er in EventRole.objects.filter(event=event):
        for mb in er.members.all():
            reset_event_links(mb.id, event.assoc_id)
    try:
        ar = AssocRole.objects.get(assoc=event.assoc, number=1)
        for mb in ar.members.all():
            reset_event_links(mb.id, event.assoc_id)
    except ObjectDoesNotExist:
        pass

    superusers = User.objects.filter(is_superuser=True)
    for user in superusers:
        reset_event_links(user.member.id, event.assoc_id)


@receiver(post_save, sender=Registration)
def post_save_registration_event_links(sender, instance, **kwargs):
    if not instance.member:
        return

    reset_event_links(instance.member.user.id, instance.run.event.assoc_id)


@receiver(post_save, sender=Event)
def post_save_event_links(sender, instance, **kwargs):
    reset_run_event_links(instance)


@receiver(post_delete, sender=Event)
def post_delete_event_links(sender, instance, **kwargs):
    reset_run_event_links(instance)


@receiver(post_save, sender=Run)
def post_save_run_links(sender, instance, **kwargs):
    reset_run_event_links(instance.event)


@receiver(post_delete, sender=Run)
def post_delete_run_links(sender, instance, **kwargs):
    reset_run_event_links(instance.event)


def reset_event_links(uid, aid):
    cache.delete(get_cache_event_key(uid, aid))


def get_cache_event_key(uid, aid):
    return f"ctx_event_links_{uid}_{aid}"
