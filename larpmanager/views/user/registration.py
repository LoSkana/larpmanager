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

import traceback
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.registration import cancel_reg
from larpmanager.cache.feature import get_assoc_features
from larpmanager.forms.registration import (
    PreRegistrationForm,
    RegistrationForm,
    RegistrationGiftForm,
)
from larpmanager.mail.base import bring_friend_instructions
from larpmanager.mail.registration import update_registration_status_bkg
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    AccountingItemOther,
    Discount,
    PaymentInvoice,
)
from larpmanager.models.association import AssocText
from larpmanager.models.event import (
    Event,
    EventText,
    PreRegistration,
)
from larpmanager.models.member import Membership, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
)
from larpmanager.models.utils import my_uuid
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import (
    get_assoc,
)
from larpmanager.utils.event import get_event, get_event_run
from larpmanager.utils.exceptions import (
    RedirectError,
    check_event_feature,
)
from larpmanager.utils.registration import check_assign_character, get_reduced_available_count, is_reg_provisional
from larpmanager.utils.text import get_assoc_text, get_event_text


@login_required
def pre_register(request, s=""):
    if s:
        ctx = get_event(request, s)
        ctx["sel"] = ctx["event"].id
        check_event_feature(request, ctx, "pre_register")
    else:
        ctx = def_user_ctx(request)
        ctx.update({"features": get_assoc_features(request.assoc["id"])})

    # get events
    ctx["choices"] = []
    ctx["already"] = []
    ctx["member"] = request.user.member

    ch = {}
    que = PreRegistration.objects.filter(member=request.user.member, event__assoc_id=request.assoc["id"])
    for el in que.order_by("pref"):
        ch[el.event.id] = True
        ctx["already"].append(el)

    for r in Event.objects.filter(assoc_id=request.assoc["id"], template=False):
        if not r.get_config("pre_register_active", False):
            continue

        if r.id in ch:
            continue

        ctx["choices"].append(r)

    if request.method == "POST":
        form = PreRegistrationForm(request.POST, ctx=ctx)
        if form.is_valid():
            nr = form.cleaned_data["new_event"]
            if nr != "":
                PreRegistration(
                    member=request.user.member,
                    event_id=nr,
                    pref=form.cleaned_data["new_pref"],
                    info=form.cleaned_data["new_info"],
                ).save()

            messages.success(request, _("Pre-registrations saved!"))
            return redirect("pre_register")
    else:
        form = PreRegistrationForm(ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/general/pre_register.html", ctx)


@login_required
def pre_register_remove(request, s):
    ctx = get_event(request, s)
    element = PreRegistration.objects.get(member=request.user.member, event=ctx["event"])
    element.delete()
    messages.success(request, _("Pre-registration cancelled!"))
    return redirect("pre_register")


@login_required
def register_exclusive(request, s, n, sc="", dis=""):
    return register(request, s, n, sc, dis)


def save_registration(request, ctx, form, run, event, reg, gift=False):
    # pprint(form.cleaned_data)
    # Create / modification registration
    if not reg:
        reg = Registration()
        reg.run = run
        reg.member = request.user.member
        if gift:
            reg.redeem_code = my_uuid(16)
        reg.save()

    provisional = is_reg_provisional(reg)

    if not gift and not provisional:
        reg.modified = reg.modified + 1

    if "info" in form.cleaned_data:
        reg.info = form.cleaned_data["info"]

    if "additionals" in form.cleaned_data:
        reg.additionals = int(form.cleaned_data["additionals"])

    if "quotas" in form.cleaned_data and form.cleaned_data["quotas"]:
        reg.quotas = int(form.cleaned_data["quotas"])
    # if reg.quotas == 2:
    # acc.value += 5
    # elif reg.quotas == 3:
    # acc.value += 10

    if "ticket" in form.cleaned_data:
        try:
            sel = RegistrationTicket.objects.filter(pk=form.cleaned_data["ticket"]).select_related("event").first()
        except Exception as err:
            raise Http404("RegistrationTicket does not exists") from err
        if sel and sel.event != event:
            raise Http404("RegistrationTicket wrong event")
        if ctx["tot_payed"] and reg.ticket and reg.ticket.price > 0 and sel.price < reg.ticket.price:
            raise Http404("lower price")
        reg.ticket = sel

    if "pay_what" in form.cleaned_data and form.cleaned_data["pay_what"]:
        reg.pay_what = int(form.cleaned_data["pay_what"])

    # Registration question
    form.save_reg_questions(reg, False)

    # Confirm saved discounts, signs
    que = AccountingItemDiscount.objects.filter(member=request.user.member, reg=reg)
    for el in que:
        if el.expires is not None:
            el.reg = reg
            el.expires = None
            el.save()

    # save reg
    reg.save()

    # special features
    if "user_character" in ctx["features"]:
        check_assign_character(request, ctx)
    if "bring_friend" in ctx["features"]:
        save_registration_bring_friend(ctx, form, reg, request)

    # send email to notify of registration update
    update_registration_status_bkg(reg.id)

    return reg


def registration_redirect(request, reg, new_reg, run):
    # check if user needs to compile membership
    if "membership" in request.assoc["features"]:
        if not request.user.member.membership.compiled:
            mes = _("To confirm your registration, please fill in your personal profile.")
            messages.success(request, mes)
            return redirect("profile")

        memb_status = request.user.member.membership.status
        if memb_status in [Membership.EMPTY, Membership.JOINED] and reg.ticket.tier != RegistrationTicket.WAITING:
            mes = _("To confirm your registration, apply to become a member of the Association.")
            messages.success(request, mes)
            return redirect("membership")

    # check if the user needs to pay
    if "payment" in request.assoc["features"]:
        if reg.alert:
            mes = _("To confirm your registration, please pay the amount indicated.")
            messages.success(request, mes)
            return redirect("acc_reg", r=reg.id)

    # all ok
    context = {"event": run}
    if new_reg:
        mes = _("Registration confirmed at %(event)s!") % context
    else:
        mes = _("Registration updated to %(event)s!") % context

    messages.success(request, mes)
    return redirect("gallery", s=reg.run.event.slug, n=reg.run.number)


def save_registration_bring_friend(ctx, form, reg, request):
    # send mail
    bring_friend_instructions(reg, ctx)
    if "bring_friend" not in form.cleaned_data:
        return
    # print(form.cleaned_data)

    # check if it has put a valid code
    cod = form.cleaned_data["bring_friend"]
    # print(cod)
    if not cod:
        return

    try:
        friend = Registration.objects.get(special_cod=cod)
    except Exception as err:
        raise Http404("I'm sorry, this friend code was not found") from err

    AccountingItemOther.objects.create(
        member=request.user.member,
        value=int(ctx["bring_friend_discount_from"]),
        run=ctx["run"],
        oth=AccountingItemOther.TOKEN,
        descr=_("You have use a friend code") + f" - {friend.member.display_member()} - {cod}",
        assoc_id=ctx["a_id"],
        ref_addit=reg.id,
    )

    AccountingItemOther.objects.create(
        member=friend.member,
        value=int(ctx["bring_friend_discount_to"]),
        run=ctx["run"],
        oth=AccountingItemOther.TOKEN,
        descr=_("Your friend code has been used") + f" - {request.user.member.display_member()} - {cod}",
        assoc_id=ctx["a_id"],
        ref_addit=friend.id,
    )

    # trigger registration accounting update
    friend.save()


def register_info(request, ctx, form, reg, dis):
    ctx["form"] = form
    ctx["lang"] = request.user.member.language
    ctx["discount_apply"] = dis
    ctx["custom_text"] = get_event_text(ctx["event"].id, EventText.REGISTER)
    ctx["event_terms_conditions"] = get_event_text(ctx["event"].id, EventText.TOC)
    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocText.TOC)
    ctx["hide_unavailable"] = ctx["event"].get_config("registration_hide_unavailable", False)

    init_form_submitted(ctx, form, request, reg)

    if reg:
        reg.provisional = is_reg_provisional(reg)

    if ctx["run"].start and "membership" in ctx["features"]:
        que = AccountingItemMembership.objects.filter(year=ctx["run"].start.year, member=request.user.member)
        if que.count() > 0:
            ctx["membership_fee"] = "done"
        elif datetime.today().year != ctx["run"].start.year:
            ctx["membership_fee"] = "future"
        else:
            ctx["membership_fee"] = "todo"

        ctx["membership_amount"] = get_assoc(request).get_config("membership_fee")


def init_form_submitted(ctx, form, request, reg=None):
    ctx["submitted"] = request.POST.dict()
    if hasattr(form, "questions"):
        for question in form.questions:
            if question.id in form.singles:
                ctx["submitted"]["q" + str(question.id)] = form.singles[question.id].option_id

    if reg:
        if reg.ticket_id:
            ctx["submitted"]["ticket"] = reg.ticket_id
        if reg.quotas:
            ctx["submitted"]["quotas"] = reg.quotas
        if reg.additionals:
            ctx["submitted"]["additionals"] = reg.additionals


@login_required
def register(request, s, n, sc="", dis="", tk=0):
    ctx = get_event_run(request, s, n, status=True)
    run = ctx["run"]
    event = ctx["event"]

    my_regs = []
    if hasattr(run, "reg"):
        my_regs.append(run.reg)

    new_reg = register_prepare(ctx, run.reg)

    ctx["ticket"] = tk

    if ctx["ticket"]:
        tick = RegistrationTicket.objects.get(pk=ctx["ticket"])
        ctx["tier"] = tick.tier
        if tick.tier == RegistrationTicket.STAFF and "closed" in run.status:
            del run.status["closed"]

    ctx["payment_feature"] = "payment" in get_assoc_features(ctx["a_id"])

    if new_reg:
        # check if there is a secret code
        if sc:
            if run.registration_secret != sc:
                raise Http404("wrong registration code")
            else:
                ctx["advance"] = True

        # check if we have to redirect it to another url to register
        elif "register_link" in ctx["features"] and event.register_link:
            if "tier" not in ctx or ctx["tier"] != RegistrationTicket.STAFF:
                return redirect(event.register_link)

        # check if we have to close registration, or send to pre-register
        elif "registration_open" in ctx["features"]:
            if not run.registration_open or run.registration_open > datetime.now():
                if "pre_register" in ctx["features"] and event.get_config("pre_register_active", False):
                    return redirect("pre_register", s=ctx["event"].slug)
                else:
                    return render(request, "larpmanager/event/not_open.html", ctx)

    if "bring_friend" in ctx["features"]:
        for config_name in ["bring_friend_discount_to", "bring_friend_discount_from"]:
            ctx[config_name] = ctx["event"].get_config(config_name, 0)

    get_user_membership(request.user.member, request.assoc["id"])
    ctx["member"] = request.user.member

    if request.method == "POST":
        form = RegistrationForm(request.POST, ctx=ctx, instance=ctx["run"].reg)
        form.sel_ticket_map(request.POST.get("ticket", ""))
        if form.is_valid():
            reg = save_registration(request, ctx, form, run, event, ctx["run"].reg)
            return registration_redirect(request, reg, new_reg, run)
    else:
        form = RegistrationForm(ctx=ctx, instance=ctx["run"].reg)

    register_info(request, ctx, form, run.reg, dis)

    return render(request, "larpmanager/event/register.html", ctx)


def register_prepare(ctx, reg):
    new_reg = True
    ctx["tot_payed"] = 0
    if reg:
        ctx["tot_payed"] = reg.tot_payed
        new_reg = False

        # we lock changing values with lower prices if there is already a payment (done or submitted)
        pending = (
            PaymentInvoice.objects.filter(
                idx=reg.id,
                member_id=reg.member_id,
                status=PaymentInvoice.SUBMITTED,
                typ=PaymentInvoice.REGISTRATION,
            ).count()
            > 0
        )
        ctx["payment_lock"] = pending or reg.tot_payed > 0

    return new_reg


def register_reduced(request, s, n):
    ctx = get_event_run(request, s, n)
    # count the number of reduced tickets
    ct = get_reduced_available_count(ctx["run"])
    return JsonResponse({"res": ct})


@login_required
def register_conditions(request, s=None):
    ctx = def_user_ctx(request)
    if s:
        ctx["event"] = get_event(request, s)["event"]
        ctx["event_text"] = get_event_text(ctx["event"].id, EventText.TOC)

    ctx["assoc_text"] = get_assoc_text(request.assoc["id"], AssocText.TOC)

    return render(request, "larpmanager/event/register_conditions.html", ctx)


# ~ def discount_bring_friend(request, ctx, cod):
# ~ # check if there is a registration with that cod
# ~ try:
# ~ friend = Registration.objects.get(special_cod=cod)
# ~ except Exception as e:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount code not valid")})
# ~ if friend.member == request.user.member:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Nice Try! But no, I'm sorry.')})
# ~ # check same event
# ~ if friend.run.event != ctx['event']:
# ~ Return Jsonresonse ({'res': 'ko', 'msg': _ ('Code applicable only to run of the same event!')})
# ~ # check future run
# ~ if friend.run.end < datetime.now().date():
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Code not valid for runs passed!')})
# ~ # get discount friend
# ~ disc = Discount.objects.get(typ=Discount.FRIEND, runs__in=[ctx['run']])
# ~ if disc.max_redeem > 0:
# ~ if AccountingItemDiscount.objects.filter(disc=disc, run=ctx['run']).count() > disc.max_redeem:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('We are sorry, the maximum number of concessions has been reached a friend')})
# ~ # check if not already registered
# ~ try:
# ~ reg = Registration.objects.get(member=request.user.member, run=ctx['run'])
# ~ if disc.only_reg:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discounts only applicable with new registrations")})
# ~ except Exception as e:
# ~ pass
# ~ # check there are no discount stores a friend
# ~ if AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx['run'], disc__typ=Discount.STANDARD).count() > 0:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount not combinable with other benefits.")})
# ~ # check the user TO don't already have the discount
# ~ try:
# ~ ac = AccountingItemDiscount.objects.get(disc=disc, member=request.user.member, run=ctx['run'])
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('You have already used a personal code')})
# ~ except Exception as e:
# ~ pass
# ~ if AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx['run'], disc__typ=Discount.PLAYAGAIN).count() > 0:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Discount not comulary with Play Again')})
# ~ # all green! proceed
# ~ now = datetime.now()
# ~ AccountingItemDiscount.objects.create(disc=disc, value=disc.value, member=request.user.member, expires=now + timedelta(minutes = 15), run=ctx['run'], detail=friend.id, assoc_id=ctx['a_id'])
# ~ Return Jsonresonse ({'res': 'ok', 'msg': _ ('The facility has been added! It was reserved for you for 15 minutes, after which it will be removed')})


@login_required
def discount(request, s, n):
    if not request.method == "POST":
        return JsonResponse({"res": "ko", "msg": "Not a post"})
    ctx = get_event_run(request, s, n)
    if "discount" not in ctx["features"]:
        return JsonResponse({"res": "ko", "msg": "Not available, kiddo"})
    cod = request.POST["cod"]
    # check if discount exists
    try:
        disc = Discount.objects.get(runs__in=[ctx["run"]], cod=cod)
    except Exception:
        # ~ try:
        # ~ return discount_bring_friend(request, ctx, cod)
        # ~ except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"res": "ko", "msg": _("Discount code not valid")})
        # delete expired accounting item
    now = datetime.now()
    AccountingItemDiscount.objects.filter(expires__lte=now).delete()
    # check if not already registered
    try:
        Registration.objects.get(member=request.user.member, run=ctx["run"], cancellation_date__isnull=True)
        if disc.only_reg:
            return JsonResponse(
                {
                    "res": "ko",
                    "msg": _("Discounts only applicable with new registrations"),
                }
            )

    except Exception:
        pass
        # check if not already used
    try:
        ac = AccountingItemDiscount.objects.get(disc=disc, member=request.user.member, reg__run=ctx["run"])
        return JsonResponse({"res": "ko", "msg": _("Code already used")})
    except Exception:
        pass
        # check if type not already used
    try:
        ac = AccountingItemDiscount.objects.get(disc__typ=disc.typ, member=request.user.member, reg__run=ctx["run"])
        return JsonResponse({"res": "ko", "msg": _("Non-cumulative code")})
    except Exception:
        pass
        # Count already used
    if disc.max_redeem > 0:
        if AccountingItemDiscount.objects.filter(disc=disc, reg__run=ctx["run"]).count() > disc.max_redeem:
            return JsonResponse(
                {
                    "res": "ko",
                    "msg": _("Sorry, this faciliation code has already been used the maximum number allowed"),
                }
            )
            # for play again, check some things
    if disc.typ == Discount.PLAYAGAIN:
        # Check there are no other applied discount stores
        if AccountingItemDiscount.objects.filter(member=request.user.member, reg__run=ctx["run"]).count() > 0:
            return JsonResponse({"res": "ko", "msg": _("Discount not combinable with other benefits.")})
        # Check that the player is enrolled in another run in the future
        if (
            Registration.objects.filter(member=request.user.member, run__event=ctx["event"])
            .exclude(run=ctx["run"])
            .count()
            == 0
        ):
            return JsonResponse(
                {
                    "res": "ko",
                    "msg": _("Discount only applicable if you are signed up for another run of the same event."),
                }
            )
    elif (
        AccountingItemDiscount.objects.filter(
            member=request.user.member, reg__run=ctx["run"], disc__typ=Discount.PLAYAGAIN
        ).count()
        > 0
    ):
        return JsonResponse({"res": "ko", "msg": _("Discount not combinable with other benefits.")})
    # ~ # for pre-register, check some things
    # ~ if disc.typ == Discount.STANDARD:
    # ~ # check there are no discount stores a friend
    # ~ if AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx['run'], disc__typ=Discount.FRIEND).count() > 0:
    # ~ Return Jsonresonse ({'res':' ko ',' msg ': _ (' discount not comulable with a friend 'door')})
    # crea accounting item
    ac = AccountingItemDiscount()
    ac.value = disc.value
    ac.member = request.user.member
    ac.expires = now + timedelta(minutes=15)
    ac.disc = disc
    ac.run = ctx["run"]
    ac.assoc_id = ctx["a_id"]
    ac.save()
    return JsonResponse(
        {
            "res": "ok",
            "msg": _(
                "The discount has been added! It has been reserved for you for 15 minutes, after "
                "which it will be removed"
            ),
        }
    )


@login_required
def discount_list(request, s, n):
    ctx = get_event_run(request, s, n)
    # delete expired accounting item
    now = datetime.now()
    # AccountingItemDiscount.objects.filter(expires__lte=now).delete()
    lst = []
    for el in AccountingItemDiscount.objects.filter(member=request.user.member, reg__run=ctx["run"]).select_related(
        "disc"
    ):
        if el.expires and el.expires < now:
            el.delete()
        else:
            lst.append(el.show())

    return JsonResponse({"lst": lst})


@login_required
def unregister(request, s, n):
    ctx = get_event_run(request, s, n, signup=True, status=True)

    # check if user is actually registered
    try:
        reg = Registration.objects.get(run=ctx["run"], member=request.user.member, cancellation_date__isnull=True)
    except ObjectDoesNotExist as err:
        raise Http404("Registration does not exist") from err

    if request.method == "POST":
        cancel_reg(reg)
        mes = _("You have correctly cancelled the registration to the %(event)s event") % {"event": ctx["event"]}
        messages.success(request, mes)
        return redirect("accounting")

    ctx["reg"] = reg
    ctx["event_terms_conditions"] = get_event_text(ctx["event"].id, EventText.TOC)
    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocText.TOC)
    return render(request, "larpmanager/event/unregister.html", ctx)


@login_required
def gift(request, s, n):
    ctx = get_event_run(request, s, n, signup=False, slug="gift", status=True)
    check_registration_open(ctx, request)

    ctx["list"] = Registration.objects.filter(
        run=ctx["run"], member=request.user.member, redeem_code__isnull=False, cancellation_date__isnull=True
    )

    info_accounting(request, ctx)

    for reg in ctx["list"]:
        for el in ctx["payments_todo"]:
            if reg.id == el.id:
                reg.payment = el

        for el in ctx["payments_pending"]:
            if reg.id == el.id:
                reg.pending = el

        for el in ctx["reg_list"]:
            if reg.id == el.id:
                reg.info = el

    return render(request, "larpmanager/event/gift.html", ctx)


def check_registration_open(ctx, request):
    if not ctx["run"].status["open"]:
        messages.warning(request, _("Registrations not open!"))
        raise RedirectError("home")


@login_required
def gift_edit(request, s, n, r):
    ctx = get_event_run(request, s, n, False, "gift", status=True)
    check_registration_open(ctx, request)

    reg = get_registration_gift(ctx, r, request)
    register_prepare(ctx, reg)

    if request.method == "POST":
        form = RegistrationGiftForm(request.POST, ctx=ctx, instance=reg)
        if form.is_valid():
            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(reg)
                messages.success(request, _("Gift card cancelled!"))
            else:
                save_registration(request, ctx, form, ctx["run"], ctx["event"], reg, gift=True)
                messages.success(request, _("Operation completed!"))
            return redirect("gift", s=s, n=n)
    else:
        form = RegistrationGiftForm(ctx=ctx, instance=reg)

    ctx["form"] = form
    ctx["gift"] = True

    init_form_submitted(ctx, form, request, reg)

    return render(request, "larpmanager/event/gift_edit.html", ctx)


def get_registration_gift(ctx, r, request):
    reg = None
    if r:
        try:
            reg = Registration.objects.get(
                pk=r,
                run=ctx["run"],
                member=request.user.member,
                redeem_code__isnull=False,
                cancellation_date__isnull=True,
            )
        except Exception as err:
            raise Http404("what are you trying to do?") from err
    return reg


@login_required
def gift_redeem(request, s, n, code):
    ctx = get_event_run(request, s, n, False, "gift", status=True)

    if ctx["run"].reg:
        messages.success(request, _("You cannot redeem a membership, you are already a member!"))
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    try:
        reg = Registration.objects.get(
            redeem_code=code,
            cancellation_date__isnull=True,
            run__event__assoc_id=ctx["a_id"],
        )
    except Exception as err:
        raise Http404("registration not found") from err

    if request.method == "POST":
        reg.member = request.user.member
        reg.redeem_code = None
        reg.save()
        messages.success(request, _("Your gifted registration has been redeemed!"))
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    ctx["reg"] = reg

    return render(request, "larpmanager/event/gift_redeem.html", ctx)
