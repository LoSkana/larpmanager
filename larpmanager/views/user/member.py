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

from calmjs.parse.asttypes import Object
from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth import login, user_logged_in
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, update_last_login
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import URLValidator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import activate, get_language
from django.utils.translation import gettext_lazy as _
from PIL import Image

from larpmanager.accounting.member import info_accounting
from larpmanager.cache.config import get_assoc_config
from larpmanager.forms.member import (
    AvatarForm,
    LanguageForm,
    MembershipConfirmForm,
    MembershipRequestForm,
    ProfileForm,
)
from larpmanager.mail.member import send_membership_confirm
from larpmanager.models.accounting import AccountingItemMembership
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
from larpmanager.models.registration import Registration
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import get_badge, get_channel, get_contact, get_member
from larpmanager.utils.exceptions import check_assoc_feature
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.member import get_leaderboard
from larpmanager.utils.pdf import get_membership_request
from larpmanager.utils.registration import registration_status
from larpmanager.utils.text import get_assoc_text


def language(request):
    """
    Handle language selection and preference setting for users.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered language form or redirect response
    """
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
    """Display and manage user profile information.

    Handles profile editing, privacy settings, and personal information updates,
    including avatar management, membership status updates, and navigation
    to membership application process when required.
    """
    if request.assoc["id"] == 0:
        return HttpResponseRedirect("/")

    ctx = def_user_ctx(request)
    member = request.user.member
    assoc_features = request.assoc["features"]
    members_fields = request.assoc["members_fields"]

    # Handle POST request (form submission)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=member, request=request)
        if form.is_valid():
            prof = form.save()

            # Update membership status
            membership = ctx["membership"]
            membership.compiled = True
            if membership.status == MembershipStatus.EMPTY:
                membership.status = MembershipStatus.JOINED
            membership.save()

            activate(prof.language)

            message = _("Personal data updated") + "!"

            # Check if membership workflow is needed
            if "membership" in assoc_features and membership.status in [
                MembershipStatus.EMPTY,
                MembershipStatus.JOINED,
            ]:
                message += " " + _("Last step, please upload your membership application") + "."
                messages.success(request, message)
                return redirect("membership")

            messages.success(request, message)
            return redirect("home")

    # Handle GET request (display form)
    else:
        form = ProfileForm(instance=member, request=request)

    ctx.update(
        {
            "form": form,
            "member": member,
            "disable_join": True,
        }
    )

    ctx["custom_text"] = get_assoc_text(request.assoc["id"], AssocTextType.PROFILE)

    # Add avatar form only if profile upload is enabled
    if "profile" in members_fields:
        ctx["avatar_form"] = AvatarForm()

    # Add profile URL only if profile image exists
    if member.profile_thumb:
        ctx["profile"] = member.profile_thumb.url

    # Add vote configuration only if voting is enabled
    if "vote" in assoc_features:
        ctx["vote_open"] = get_assoc_config(ctx["membership"].assoc_id, "vote_open", False)

    return render(request, "larpmanager/member/profile.html", ctx)


def load_profile(request, img, ext):
    n_path = f"member/{request.user.member.pk}_{uuid4().hex}.{ext}"
    request.user.member.profile = n_path
    request.user.member.save()
    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_upload(request):
    """Handle profile image upload for authenticated users.

    Args:
        request: HTTP request object containing POST data and uploaded image file

    Returns:
        JsonResponse: Success/failure status and image URL on success
    """
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
    """Rotate user's profile image 90 degrees clockwise or counterclockwise.

    Args:
        request: Django HTTP request object
        n: Rotation direction (1 for clockwise, other for counterclockwise)

    Returns:
        JsonResponse with success/failure status and new image URL
    """
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
    """User interface for managing their own membership status.

    Handles membership applications, renewals, and membership-related
    form submissions for individual users.
    """
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
    """Display public member profile information.

    Shows publicly visible member data while respecting privacy settings,
    including badges, registration history, and character information
    based on association configuration and feature availability.
    """
    ctx = def_user_ctx(request)
    ctx.update(get_member(n))

    if not Membership.objects.filter(member=ctx["member"], assoc_id=request.assoc["id"]).exists():
        raise Http404("no membership")

    if "badge" in request.assoc["features"]:
        ctx["badges"] = []
        for badge in ctx["member"].badges.filter(assoc_id=request.assoc["id"]).order_by("number"):
            ctx["badges"].append(badge.show(request.LANGUAGE_CODE))

    assoc_id = ctx["a_id"]
    if get_assoc_config(assoc_id, "player_larp_history", False):
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

            for rcr in el.rcrs.select_related("character").all():
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
    """Handle chat functionality between members.

    Manages message exchange, conversation history, and chat permissions
    within the association context for member-to-member communication.
    """
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
    """Display paginated leaderboard of members with badge scores.

    Args:
        request: Django HTTP request object
        p: Page number for pagination (default: 1)

    Returns:
        Rendered leaderboard page with member rankings
    """
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
    """Handle voting functionality for association members.

    Manages voting processes, ballot submissions, and vote counting
    for association governance and decision-making.
    """
    check_assoc_feature(request, "vote")
    ctx = def_user_ctx(request)
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})

    ctx["year"] = datetime.now().year

    # check if they have payed
    if "membership" in request.assoc["features"]:
        que = AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=ctx["year"])
        if not que.filter(member_id=ctx["member"].id).exists():
            messages.error(request, _("You must complete payment of membership dues in order to vote!"))
            return redirect("acc_membership")

    que = Vote.objects.filter(member=ctx["member"], assoc_id=ctx["a_id"], year=ctx["year"])
    if que.count() > 0:
        ctx["done"] = True
        return render(request, "larpmanager/member/vote.html", ctx)

    assoc_id = ctx["a_id"]

    config_holder = Object()

    ctx["vote_open"] = get_assoc_config(assoc_id, "vote_open", False, config_holder)
    ctx["vote_cands"] = get_assoc_config(assoc_id, "vote_candidates", "", config_holder).split(",")
    ctx["vote_min"] = get_assoc_config(assoc_id, "vote_min", "1", config_holder)
    ctx["vote_max"] = get_assoc_config(assoc_id, "vote_max", "1", config_holder)

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
def delegated(request: HttpRequest) -> HttpResponse:
    """Manage delegated member accounts for parent-child member relationships.

    Allows parent members to create and switch between delegated child accounts,
    useful for managing family memberships or multiple personas. Supports
    bidirectional switching between parent and delegated accounts with
    proper authentication handling.

    Args:
        request: HTTP request object with authenticated user

    Returns:
        HttpResponse: Rendered delegated accounts page or redirect after login switch

    Side effects:
        - May create new delegated user accounts
        - Logs user in as different member (parent or child)
        - Disconnects last login update signal temporarily
    """
    # Ensure delegated members feature is enabled
    check_assoc_feature(request, "delegated_members")
    ctx = def_user_ctx(request)

    # Disable last login update to avoid tracking when switching accounts
    user_logged_in.disconnect(update_last_login, dispatch_uid="update_last_login")
    backend = get_user_backend()

    # Handle delegated user trying to return to parent account
    if request.user.member.parent:
        if request.method == "POST":
            # Log back in as parent account
            login(request, request.user.member.parent.user, backend=backend)
            messages.success(
                request, _("You are now logged in with your main account") + ":" + str(request.user.member)
            )
            return redirect("home")
        # Show option to return to parent account
        return render(request, "larpmanager/member/delegated.html", ctx)

    # Handle parent account managing delegated accounts
    # Retrieve all delegated child accounts for this parent
    ctx["list"] = Member.objects.filter(parent=request.user.member)
    del_dict = {el.id: el for el in ctx["list"]}

    # Process POST requests for account switching or creation
    if request.method == "POST":
        account_login = request.POST.get("account")
        # Handle switching to an existing delegated account
        if account_login:
            account_login = int(account_login)
            if account_login not in del_dict:
                raise Http404(f"delegated account not found: {account_login}")
            delegated = del_dict[account_login]
            # Log in as the selected delegated account
            login(request, delegated.user, backend=backend)
            messages.success(request, _("You are now logged in with the delegate account") + ":" + str(delegated))
            return redirect("home")

        # Handle creating a new delegated account
        form = ProfileForm(request.POST, request=request)
        if form.is_valid():
            data = form.cleaned_data
            # Generate unique username and email for delegated account
            username = f"{data['name']}_{data['surname']}".lower()
            email = f"{username}@larpmanager.com"
            password = generate_id(32)
            user = User.objects.create_user(username=username, email=email, password=password)

            # Copy profile data to delegated member
            for field in data:
                setattr(user.member, field, data[field])
            # Link delegated member to parent
            user.member.parent = request.user.member
            user.member.save()

            # Mark membership as compiled for new delegated account
            mb = get_user_membership(user.member, request.assoc["id"])
            mb.compiled = True
            mb.save()

            messages.success(request, _("New delegate user added!"))
            return redirect("delegated")
    else:
        # Display form for creating new delegated account
        form = ProfileForm(request=request)

    ctx["form"] = form

    # Add accounting information for each delegated account
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
    """
    Display user's registrations with status information.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered registrations template
    """
    nt = []
    # get all registrations in the future
    for reg in Registration.objects.filter(member=request.user.member, run__event_id=request.assoc["id"]):
        registration_status(reg.run, request.user)
        nt.append(reg)
    return render(request, "larpmanager/member/registrations.html", {"reg_list": nt})
