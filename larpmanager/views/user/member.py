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

import math
import os
import random
from datetime import date, datetime
from uuid import uuid4

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth import login, user_logged_in
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, update_last_login
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import URLValidator
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import activate, get_language
from django.utils.translation import gettext_lazy as _
from PIL import Image

from larpmanager.accounting.member import info_accounting
from larpmanager.forms.member import (
    AvatarForm,
    LanguageForm,
    MembershipConfirmForm,
    MembershipRequestForm,
    ProfileForm,
)
from larpmanager.mail.member import send_membership_confirm
from larpmanager.models.accounting import (
    AccountingItemMembership,
)
from larpmanager.models.association import Association, AssocTextType
from larpmanager.models.member import (
    Badge,
    Member,
    Membership,
    MembershipStatus,
    NewsletterChoices,
    Vote,
    get_user_membership,
)
from larpmanager.models.miscellanea import (
    ChatMessage,
    Contact,
)
from larpmanager.models.registration import (
    Registration,
)
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import get_badge, get_channel, get_contact, get_member
from larpmanager.utils.exceptions import (
    check_assoc_feature,
)
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.member import get_leaderboard
from larpmanager.utils.pdf import (
    get_membership_request,
)
from larpmanager.utils.registration import registration_status
from larpmanager.utils.text import get_assoc_text


def language(request):
    if request.user.is_authenticated:
        current_language = request.user.member.language
    else:
        current_language = get_language()

    if request.method == "POST":
        form = LanguageForm(request.POST, current_language=current_language)
        if form.is_valid():
            language = form.cleaned_data["language"]
            activate(language)
            request.session["django_language"] = language
            response = HttpResponseRedirect("/")
            if request.user.is_authenticated:
                request.user.member.language = language
                request.user.member.save()
            else:
                response.set_cookie(
                    conf_settings.LANGUAGE_COOKIE_NAME,
                    language,
                    max_age=conf_settings.LANGUAGE_COOKIE_AGE,
                    path=conf_settings.LANGUAGE_COOKIE_PATH,
                    domain=conf_settings.LANGUAGE_COOKIE_DOMAIN,
                    secure=conf_settings.SESSION_COOKIE_SECURE or None,
                    httponly=False,
                    samesite=conf_settings.SESSION_COOKIE_SAMESITE,
                )
            return response
    else:
        form = LanguageForm(current_language=current_language)
    return render(request, "larpmanager/member/language.html", {"form": form})


@login_required
def profile(request):
    if request.assoc["id"] == 0:
        return HttpResponseRedirect("/")

    ctx = def_user_ctx(request)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user.member, request=request)
        if form.is_valid():
            prof = form.save()
            ctx["membership"].compiled = True
            if ctx["membership"].status == MembershipStatus.EMPTY:
                ctx["membership"].status = MembershipStatus.JOINED
            ctx["membership"].save()
            activate(prof.language)

            mes = _("Personal data updated") + "!"

            if "membership" in request.assoc["features"]:
                if ctx["membership"].status in [MembershipStatus.EMPTY, MembershipStatus.JOINED]:
                    mes += " " + _("Last step, please upload your membership application") + "."
                    messages.success(request, mes)
                    return redirect("membership")

            messages.success(request, mes)
            return redirect("home")
    else:
        form = ProfileForm(instance=request.user.member, request=request)

    ctx["form"] = form
    ctx["member"] = request.user.member
    ctx["custom_text"] = get_assoc_text(request.assoc["id"], AssocTextType.PROFILE)

    if "profile" in request.assoc["members_fields"]:
        ctx["avatar_form"] = AvatarForm()

    if request.user.member.profile_thumb:
        ctx["profile"] = request.user.member.profile_thumb.url

    # print(p)

    # ~ if p and "membership" in p:
    # ~ # messages.sucesss (Request, _ ('To register, we have to ask you some data. It will take very little, we jurist it!'))
    # ~ ctx["membership"] = True

    if "vote" in request.assoc["features"]:
        ctx["vote_open"] = ctx["membership"].assoc.get_config("vote_open", False)

    ctx["disable_join"] = True

    return render(request, "larpmanager/member/profile.html", ctx)


def load_profile(request, img, ext):
    n_path = f"member/{request.user.member.pk}_{uuid4().hex}.{ext}"
    request.user.member.profile = n_path
    request.user.member.save()
    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_upload(request):
    if not request.method == "POST":
        return JsonResponse({"res": "ko"})

    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"res": "ko"})

    img = form.cleaned_data["image"]
    ext = img.name.split(".")[-1]

    n_path = f"member/{request.user.member.pk}_{uuid4().hex}.{ext}"

    path = default_storage.save(n_path, ContentFile(img.read()))

    request.user.member.profile = path
    request.user.member.save()

    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_rotate(request, n):
    path = str(request.user.member.profile)
    if not path:
        return JsonResponse({"res": "ko"})

    path = os.path.join(conf_settings.MEDIA_ROOT, path)
    im = Image.open(path)
    if n == 1:
        out = im.rotate(90)
    else:
        out = im.rotate(-90)

    ext = path.split(".")[-1]

    n_path = f"{os.path.dirname(path)}/{request.user.member.pk}_{uuid4().hex}.{ext}"
    out.save(n_path)

    request.user.member.profile = n_path
    request.user.member.save()

    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_privacy(request):
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "member": request.user.member,
            "joined": request.user.member.memberships.exclude(status=MembershipStatus.EMPTY).exclude(
                status=MembershipStatus.REWOKED
            ),
        }
    )
    return render(request, "larpmanager/member/privacy.html", ctx)


@login_required
def profile_privacy_rewoke(request, slug):
    ctx = def_user_ctx(request)
    ctx.update({"member": request.user.member})
    try:
        assoc = Association.objects.get(slug=slug)
        membership = Membership.objects.get(assoc=assoc, member=request.user.member)
        membership.status = MembershipStatus.EMPTY
        membership.save()
        messages.success(request, _("Data share removed successfully") + "!")
    except Exception as err:
        raise Http404("error in performing request") from err
    return redirect("profile_privacy")


@login_required
def membership(request):
    ctx = def_user_ctx(request)

    el = get_user_membership(request.user.member, request.assoc["id"])

    if not el.compiled:
        return redirect("profile")

    if request.method == "POST":
        if el.status not in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            raise Http404("wrong membership")

        # Second pass - if the user already uploaded the files
        if el.status == MembershipStatus.UPLOADED:
            form = MembershipConfirmForm(request.POST, request.FILES)
            if form.is_valid():
                el.status = MembershipStatus.SUBMITTED
                el.save()
                send_membership_confirm(request, el)
                mes = _("Your membership application was successfully submitted!")
                messages.success(request, mes)
                return redirect("home")

        # First pass - if the user did not upload the files
        else:
            form = MembershipRequestForm(request.POST, request.FILES, instance=el)
            if form.is_valid():
                form.save()
                el.status = MembershipStatus.UPLOADED
                el.save()
                form = MembershipConfirmForm()
                ctx["doc_path"] = el.get_document_filepath().lower()
                ctx["req_path"] = el.get_request_filepath().lower()

    else:
        # Bring back to empty if uploaded
        if el.status == MembershipStatus.UPLOADED:
            el.status = MembershipStatus.JOINED
            el.save()
        form = MembershipRequestForm(instance=el)

    ctx.update({"member": request.user.member, "membership": el, "form": form})

    if "fiscal_code_check" in ctx["features"]:
        ctx.update(calculate_fiscal_code(ctx["member"]))

    ctx["fee_payed"] = AccountingItemMembership.objects.filter(
        assoc_id=request.assoc["id"],
        year=datetime.now().year,
        member_id=request.user.member.id,
    ).exists()

    if el.status == MembershipStatus.ACCEPTED:
        ctx["statute"] = get_assoc_text(request.assoc["id"], AssocTextType.STATUTE)

    ctx["disable_join"] = True

    return render(request, "larpmanager/member/membership.html", ctx)


@login_required
def membership_request(request):
    ctx = def_user_ctx(request)
    ctx["member"] = request.user.member
    return get_membership_request(ctx)


@login_required
def membership_request_test(request):
    ctx = def_user_ctx(request)
    ctx.update({"member": request.user.member})
    return render(request, "pdf/membership/request.html", ctx)


@login_required
def public(request, n):
    ctx = def_user_ctx(request)
    ctx.update(get_member(n))

    if Membership.objects.filter(member=ctx["member"], assoc_id=request.assoc["id"]).count() == 0:
        raise Http404("no membership")

    if "badge" in request.assoc["features"]:
        ctx["badges"] = []
        for badge in ctx["member"].badges.filter(assoc_id=request.assoc["id"]).order_by("number"):
            ctx["badges"].append(badge.show(request.LANGUAGE_CODE))

    assoc = Association.objects.get(pk=ctx["a_id"])
    if assoc.get_config("player_larp_history", False):
        ctx["regs"] = (
            Registration.objects.filter(
                cancellation_date__isnull=True,
                member=ctx["member"],
                run__event__assoc_id=request.assoc["id"],
            )
            .order_by("-run__end")
            .select_related("run", "run__event")
            .prefetch_related("rcrs")
        )
        for el in ctx["regs"]:
            el.chars = {}

            for rcr in el.rcrs.all():
                if not rcr.character:
                    continue
                name = rcr.character.name
                if rcr.custom_name:
                    name = rcr.custom_name
                el.chars[rcr.character.number] = name

    validate = URLValidator()
    if ctx["member"].social_contact:
        try:
            validate(ctx["member"].social_contact)
            ctx["member"].contact_url = True
        except Exception:
            pass

    return render(request, "larpmanager/member/public.html", ctx)


@login_required
def chats(request):
    check_assoc_feature(request, "chat")
    ctx = def_user_ctx(request)
    ctx.update(
        {"list": Contact.objects.filter(me=request.user.member, assoc_id=request.assoc["id"]).order_by("-last_message")}
    )
    return render(request, "larpmanager/member/chats.html", ctx)


@login_required
def chat(request, n):
    check_assoc_feature(request, "chat")
    mid = request.user.member.id
    if n == mid:
        messages.success(request, _("You can't send messages to yourself") + "!")
        return redirect("home")
    ctx = get_member(n)
    yid = ctx["member"].id
    channel = get_channel(yid, mid)
    if request.method == "POST":
        tx = request.POST["text"]
        if len(tx) > 0:
            ChatMessage(
                sender_id=mid,
                receiver_id=yid,
                channel=channel,
                message=tx,
                assoc_id=request.assoc["id"],
            ).save()
            your_contact = get_contact(yid, mid)
            if not your_contact:
                your_contact = Contact(
                    me_id=yid,
                    you_id=mid,
                    channel=get_channel(mid, yid),
                    assoc_id=request.assoc["id"],
                )
            your_contact.num_unread += 1
            your_contact.last_message = datetime.now()
            your_contact.save()
            mine_contact = get_contact(mid, yid)
            if not mine_contact:
                mine_contact = Contact(
                    me_id=mid,
                    you_id=yid,
                    channel=get_channel(mid, yid),
                    assoc_id=request.assoc["id"],
                )
            mine_contact.last_message = datetime.now()
            mine_contact.save()
            messages.success(request, _("Message sent!"))
            return redirect(request.path_info)

    mine_contact = get_contact(mid, yid)
    if mine_contact:
        mine_contact.num_unread = 0
        mine_contact.save()
    ctx["list"] = ChatMessage.objects.filter(channel=channel, assoc_id=request.assoc["id"]).order_by("-created")
    return render(request, "larpmanager/member/chat.html", ctx)


@login_required
def badges(request):
    ctx = def_user_ctx(request)
    ctx.update({"badges": []})
    check_assoc_feature(request, "badge")
    for badge in Badge.objects.filter(assoc_id=request.assoc["id"]).order_by("number"):
        ctx["badges"].append(badge.show(request.LANGUAGE_CODE))
    ctx["page"] = "badges"
    return render(request, "larpmanager/general/badges.html", ctx)


@login_required
def badge(request, n, p=1):
    check_assoc_feature(request, "badge")
    badge = get_badge(n, request)
    ctx = def_user_ctx(request)
    ctx.update({"badge": badge.show(request.LANGUAGE_CODE), "list": []})
    for el in badge.members.all():
        ctx["list"].append(el)
    v = datetime.today().date() - date(1970, 1, 1)
    random.Random(v.days).shuffle(ctx["list"])
    return render(request, "larpmanager/general/badge.html", ctx)


@login_required
def leaderboard(request, p=1):
    check_assoc_feature(request, "badge")
    member_list = get_leaderboard(request.assoc["id"])
    num_el = 25
    num_pages = math.ceil(len(member_list) / num_el)
    if p < 0:
        p = 1
    p = min(p, num_pages)
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "pages": member_list[(p - 1) * num_el : p * num_el],
            "num_pages": num_pages,
            "number": p,
            "previous_page_number": p - 1,
            "next_page_number": p + 1,
        }
    )
    ctx["page"] = "leaderboard"
    return render(request, "larpmanager/general/leaderboard.html", ctx)


@login_required
def unsubscribe(request):
    ctx = def_user_ctx(request)
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})
    mb = get_user_membership(ctx["member"], ctx["a_id"])
    mb.newsletter = NewsletterChoices.NO
    mb.save()
    messages.success(request, _("The request of removal from further communication has been successfull!"))
    return redirect("home")


@login_required
def vote(request):
    check_assoc_feature(request, "vote")
    ctx = def_user_ctx(request)
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})

    ctx["year"] = datetime.now().year

    # check if they have payed
    if "membership" in request.assoc["features"]:
        que = AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=ctx["year"])
        if que.filter(member_id=ctx["member"].id).count() == 0:
            messages.error(request, _("You must complete payment of membership dues in order to vote!"))
            return redirect("acc_membership")

    que = Vote.objects.filter(member=ctx["member"], assoc_id=ctx["a_id"], year=ctx["year"])
    if que.count() > 0:
        ctx["done"] = True
        return render(request, "larpmanager/member/vote.html", ctx)

    assoc = Association.objects.get(pk=ctx["a_id"])

    ctx["vote_open"] = assoc.get_config("vote_open", False)
    ctx["vote_cands"] = assoc.get_config("vote_candidates", "").split(",")
    ctx["vote_min"] = assoc.get_config("vote_min", "1")
    ctx["vote_max"] = assoc.get_config("vote_max", "1")

    if request.method == "POST":
        cnt = 0
        for m_id in ctx["vote_cands"]:
            v = request.POST.get(f"vote_{m_id}")
            if not v:
                continue
            cnt += 1
            Vote.objects.create(
                member=ctx["member"],
                assoc_id=ctx["a_id"],
                year=ctx["year"],
                number=cnt,
                candidate_id=m_id,
            )
        return redirect(request.path_info)

    ctx["candidates"] = []

    for mb in ctx["vote_cands"]:
        try:
            idx = int(mb)
            ctx["candidates"].append(Member.objects.get(pk=idx))
        except Exception:
            pass
    random.shuffle(ctx["candidates"])

    return render(request, "larpmanager/member/vote.html", ctx)


# ## DELEGATED ###


@login_required
def delegated(request):
    check_assoc_feature(request, "delegated_members")
    ctx = def_user_ctx(request)

    user_logged_in.disconnect(update_last_login, dispatch_uid="update_last_login")
    backend = get_user_backend()

    # If the user is delegated, show info on login to the main account
    if request.user.member.parent:
        if request.method == "POST":
            login(request, request.user.member.parent.user, backend=backend)
            messages.success(
                request, _("You are now logged in with your main account") + ":" + str(request.user.member)
            )
            return redirect("home")
        return render(request, "larpmanager/member/delegated.html", ctx)

    # If the user is the main, recover the list of delegated accounts
    ctx["list"] = Member.objects.filter(parent=request.user.member)
    del_dict = {el.id: el for el in ctx["list"]}

    if request.method == "POST":
        account_login = request.POST.get("account")
        if account_login:
            account_login = int(account_login)
            if account_login not in del_dict:
                raise Http404(f"delegated account not found: {account_login}")
            delegated = del_dict[account_login]
            login(request, delegated.user, backend=backend)
            messages.success(request, _("You are now logged in with the delegate account") + ":" + str(delegated))
            return redirect("home")

        form = ProfileForm(request.POST, request=request)
        if form.is_valid():
            data = form.cleaned_data
            username = f"{data['name']}_{data['surname']}".lower()
            email = f"{username}@larpmanager.com"
            password = generate_id(32)
            user = User.objects.create_user(username=username, email=email, password=password)

            for field in data:
                setattr(user.member, field, data[field])
            user.member.parent = request.user.member
            user.member.save()

            mb = get_user_membership(user.member, request.assoc["id"])
            mb.compiled = True
            mb.save()

            messages.success(request, _("New delegate user added!"))
            return redirect("delegated")
    else:
        form = ProfileForm(request=request)

    ctx["form"] = form

    for el in ctx["list"]:
        del_ctx = {"member": el, "a_id": ctx["a_id"]}
        info_accounting(request, del_ctx)
        el.ctx = del_ctx
    return render(request, "larpmanager/member/delegated.html", ctx)


def get_user_backend():
    backend = "allauth.account.auth_backends.AuthenticationBackend"
    return backend


@login_required
def registrations(request):
    nt = []
    # get all registrations in the future
    for reg in Registration.objects.filter(member=request.user.member, run__event_id=request.assoc["id"]):
        registration_status(reg.run, request.user)
        nt.append(reg)
    return render(request, "larpmanager/member/registrations.html", {"reg_list": nt})
