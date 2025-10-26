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
from larpmanager.utils.base import get_context
from larpmanager.utils.common import get_badge, get_channel, get_contact, get_member
from larpmanager.utils.exceptions import check_assoc_feature
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.member import get_leaderboard
from larpmanager.utils.pdf import get_membership_request
from larpmanager.utils.registration import registration_status
from larpmanager.utils.text import get_assoc_text
from larpmanager.views.user.event import get_character_rels_dict, get_payment_invoices_dict, get_pre_registrations_dict


def language(request: HttpRequest) -> HttpResponse:
    """Handle language selection and preference setting for users.

    This view processes language selection forms and updates user language preferences.
    For authenticated users, the language preference is saved to their member profile.
    For anonymous users, the language is stored in cookies and session.

    Args:
        request: The HTTP request object containing user data and form submission.

    Returns:
        HttpResponse: Either a rendered language selection form (GET) or a redirect
                     response after successful language change (POST).

    Note:
        Language changes are immediately activated and stored in the session.
        Authenticated users have their preference saved to the database.
    """
    # Determine current language based on user authentication status
    if request.user.is_authenticated:
        current_language = request.user.member.language
    else:
        current_language = get_language()

    # Process form submission for language change
    if request.method == "POST":
        form = LanguageForm(request.POST, current_language=current_language)
        if form.is_valid():
            language = form.cleaned_data["language"]

            # Activate the new language and store in session
            activate(language)
            request.session["django_language"] = language
            response = HttpResponseRedirect("/")

            # Save language preference for authenticated users
            if request.user.is_authenticated:
                request.user.member.language = language
                request.user.member.save()
            else:
                # Set language cookie for anonymous users
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
        # Display language selection form for GET requests
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

    context = get_context(request)
    member = request.user.member
    assoc_features = request.assoc["features"]
    members_fields = request.assoc["members_fields"]

    # Handle POST request (form submission)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=member, request=request)
        if form.is_valid():
            prof = form.save()

            # Update membership status
            membership = context["membership"]
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

    context.update(
        {
            "form": form,
            "member": member,
            "disable_join": True,
        }
    )

    context["custom_text"] = get_assoc_text(context["association_id"], AssocTextType.PROFILE)

    # Add avatar form only if profile upload is enabled
    if "profile" in members_fields:
        context["avatar_form"] = AvatarForm()

    # Add profile URL only if profile image exists
    if member.profile_thumb:
        context["profile"] = member.profile_thumb.url

    # Add vote configuration only if voting is enabled
    if "vote" in assoc_features:
        context["vote_open"] = get_assoc_config(context["membership"].assoc_id, "vote_open", False, context)

    return render(request, "larpmanager/member/profile.html", context)


def load_profile(request: HttpRequest, img, ext: str) -> JsonResponse:
    """Save uploaded profile image and return thumbnail URL."""
    # Generate unique filename and save to member profile
    n_path = f"member/{request.user.member.pk}_{uuid4().hex}.{ext}"
    request.user.member.profile = n_path
    request.user.member.save()

    # Return success response with thumbnail URL
    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_upload(request: HttpRequest) -> JsonResponse:
    """Handle profile image upload for authenticated users.

    This function processes POST requests containing profile image uploads,
    validates the uploaded file, saves it to storage with a unique filename,
    and updates the user's member profile.

    Args:
        request (HttpRequest): HTTP request object containing POST data and
            uploaded image file in the 'image' field.

    Returns:
        JsonResponse: JSON response containing:
            - "res": "ok" on success, "ko" on failure
            - "src": URL of the uploaded image thumbnail on success

    Note:
        Requires authenticated user with associated member object.
        Only accepts POST requests with valid image files.
    """
    # Only accept POST requests
    if not request.method == "POST":
        return JsonResponse({"res": "ko"})

    # Validate uploaded image using form
    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"res": "ko"})

    # Extract image and file extension
    img = form.cleaned_data["image"]
    ext = img.name.split(".")[-1]

    # Generate unique filename with member ID and UUID
    n_path = f"member/{request.user.member.pk}_{uuid4().hex}.{ext}"

    # Save file to storage and get the actual path
    path = default_storage.save(n_path, ContentFile(img.read()))

    # Update member profile with new image path
    request.user.member.profile = path
    request.user.member.save()

    # Return success response with thumbnail URL
    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_rotate(request: HttpRequest, n: int) -> JsonResponse:
    """Rotate user's profile image 90 degrees clockwise or counterclockwise.

    Args:
        request: Django HTTP request object containing authenticated user
        n: Rotation direction indicator (1 for clockwise, any other value for counterclockwise)

    Returns:
        JsonResponse: Contains status ('ok'/'ko') and optionally the new thumbnail URL
            - Success: {"res": "ok", "src": "<thumbnail_url>"}
            - Failure: {"res": "ko"}

    Raises:
        IOError: If image file cannot be opened or saved
        AttributeError: If user has no associated member or profile
    """
    # Get the current profile image path
    path = str(request.user.member.profile)
    if not path:
        return JsonResponse({"res": "ko"})

    # Build full filesystem path and open image
    path = os.path.join(conf_settings.MEDIA_ROOT, path)
    im = Image.open(path)

    # Rotate image based on direction parameter
    if n == 1:
        out = im.rotate(90)  # Clockwise rotation
    else:
        out = im.rotate(-90)  # Counterclockwise rotation

    # Extract file extension and generate new unique filename
    ext = path.split(".")[-1]
    n_path = f"{os.path.dirname(path)}/{request.user.member.pk}_{uuid4().hex}.{ext}"

    # Save rotated image and update member profile
    out.save(n_path)
    request.user.member.profile = n_path
    request.user.member.save()

    # Return success response with thumbnail URL
    return JsonResponse({"res": "ok", "src": request.user.member.profile_thumb.url})


@login_required
def profile_privacy(request: HttpRequest) -> HttpResponse:
    """Display user's privacy profile page with membership information.

    Shows the user's privacy settings and their active memberships,
    excluding empty and revoked memberships.

    Args:
        request: The HTTP request object containing user information.

    Returns:
        HttpResponse: Rendered privacy template with user context and memberships.
    """
    # Get default user context for the request
    context = get_context(request)

    # Add member-specific data to context
    context.update(
        {
            "member": request.user.member,
            # Get active memberships, excluding empty and revoked ones
            "joined": request.user.member.memberships.exclude(status=MembershipStatus.EMPTY).exclude(
                status=MembershipStatus.REWOKED
            ),
        }
    )

    # Render and return the privacy template with context
    return render(request, "larpmanager/member/privacy.html", context)


@login_required
def profile_privacy_rewoke(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Revoke data sharing permission for a user's membership in an association.

    Sets the membership status to EMPTY, effectively removing data sharing consent
    for the user's membership in the specified association.

    Args:
        request: The HTTP request object containing user information
        slug: The URL slug identifier for the association

    Returns:
        HttpResponse: Redirect to the profile_privacy page

    Raises:
        Http404: When association or membership is not found, or other errors occur
    """
    # Initialize context with default user data
    context = get_context(request)
    context.update({"member": request.user.member})

    try:
        # Retrieve the association by slug
        assoc = Association.objects.get(slug=slug)

        # Get the user's membership for this association
        membership = Membership.objects.get(assoc=assoc, member=request.user.member)

        # Revoke data sharing by setting status to EMPTY
        membership.status = MembershipStatus.EMPTY
        membership.save()

        # Notify user of successful operation
        messages.success(request, _("Data share removed successfully") + "!")
    except Exception as err:
        # Handle any errors by raising 404
        raise Http404("error in performing request") from err

    # Redirect back to privacy settings page
    return redirect("profile_privacy")


@login_required
def membership(request: HttpRequest) -> HttpResponse:
    """User interface for managing their own membership status.

    Handles membership applications, renewals, and membership-related
    form submissions for individual users.

    Args:
        request: The HTTP request object containing user and POST data.

    Returns:
        HttpResponse: Rendered membership template or redirect response.

    Raises:
        Http404: If membership status is invalid for the requested operation.
    """
    # Initialize context with default user context
    context = get_context(request)

    # Get user's membership record for current association
    el = get_user_membership(request.user.member, context["association_id"])

    # Redirect to profile if membership compilation is incomplete
    if not el.compiled:
        return redirect("profile")

    if request.method == "POST":
        # Validate membership status allows form submission
        if el.status not in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            raise Http404("wrong membership")

        # Second pass - confirmation after file upload
        if el.status == MembershipStatus.UPLOADED:
            form = MembershipConfirmForm(request.POST, request.FILES)
            if form.is_valid():
                # Mark membership as submitted and send confirmation
                el.status = MembershipStatus.SUBMITTED
                el.save()
                send_membership_confirm(request, el)

                # Show success message and redirect to home
                mes = _("Your membership application was successfully submitted!")
                messages.success(request, mes)
                return redirect("home")

        # First pass - initial file upload
        else:
            form = MembershipRequestForm(request.POST, request.FILES, instance=el)
            if form.is_valid():
                # Save form data and update status to uploaded
                form.save()
                el.status = MembershipStatus.UPLOADED
                el.save()

                # Prepare confirmation form and file paths for template
                form = MembershipConfirmForm()
                context["doc_path"] = el.get_document_filepath().lower()
                context["req_path"] = el.get_request_filepath().lower()

    else:
        # Reset status if returning from uploaded state
        if el.status == MembershipStatus.UPLOADED:
            el.status = MembershipStatus.JOINED
            el.save()

        # Initialize form with current membership data
        form = MembershipRequestForm(instance=el)

    # Add core membership data to context
    context.update({"member": request.user.member, "membership": el, "form": form})

    # Add fiscal code calculation if feature is enabled
    if "fiscal_code_check" in context["features"]:
        context.update(calculate_fiscal_code(context["member"]))

    # Check if membership fee has been paid for current year
    context["fee_payed"] = AccountingItemMembership.objects.filter(
        assoc_id=context["association_id"],
        year=datetime.now().year,
        member_id=request.user.member.id,
    ).exists()

    # Add statute text for accepted memberships
    if el.status == MembershipStatus.ACCEPTED:
        context["statute"] = get_assoc_text(context["association_id"], AssocTextType.STATUTE)

    # Disable join functionality for this view
    context["disable_join"] = True

    return render(request, "larpmanager/member/membership.html", context)


@login_required
def membership_request(request: HttpRequest) -> HttpResponse:
    """Handle membership request display for the current user."""
    context = get_context(request)
    context["member"] = request.user.member
    return get_membership_request(context)


@login_required
def membership_request_test(request: HttpRequest) -> HttpResponse:
    """Render membership request test PDF template."""
    context = get_context(request)
    context.update({"member": request.user.member})
    return render(request, "pdf/membership/request.html", context)


@login_required
def public(request: HttpRequest, n: int) -> HttpResponse:
    """Display public member profile information.

    Shows publicly visible member data while respecting privacy settings,
    including badges, registration history, and character information
    based on association configuration and feature availability.

    Args:
        request: HTTP request object containing user and association context
        n: Member ID to display profile for

    Returns:
        HttpResponse: Rendered public member profile page

    Raises:
        Http404: If member has no membership in the current association
    """
    # Initialize context with user data and fetch member information
    context = get_context(request)
    context.update(get_member(n))

    # Verify member has membership in current association
    if not Membership.objects.filter(member=context["member"], assoc_id=context["association_id"]).exists():
        raise Http404("no membership")

    # Add badges if badge feature is enabled for association
    if "badge" in request.assoc["features"]:
        context["badges"] = []
        for badge in context["member"].badges.filter(assoc_id=context["association_id"]).order_by("number"):
            context["badges"].append(badge.show(request.LANGUAGE_CODE))

    # Add LARP history if enabled in association configuration
    assoc_id = context["association_id"]
    if get_assoc_config(assoc_id, "player_larp_history", False):
        # Fetch registrations with related run and event data
        context["regs"] = (
            Registration.objects.filter(
                cancellation_date__isnull=True,
                member=context["member"],
                run__event__assoc_id=context["association_id"],
            )
            .order_by("-run__end")
            .select_related("run", "run__event")
            .prefetch_related("rcrs")
        )

        # Process character information for each registration
        for el in context["regs"]:
            el.chars = {}

            for rcr in el.rcrs.select_related("character").all():
                if not rcr.character:
                    continue
                # Use custom name if available, otherwise use character name
                name = rcr.character.name
                if rcr.custom_name:
                    name = rcr.custom_name
                el.chars[rcr.character.number] = name

    # Validate and mark social contact as URL if valid
    validate = URLValidator()
    if context["member"].social_contact:
        try:
            validate(context["member"].social_contact)
            context["member"].contact_url = True
        except Exception:
            pass

    return render(request, "larpmanager/member/public.html", context)


@login_required
def chats(request: HttpRequest) -> HttpResponse:
    """Render chat list page for the current user."""
    # Check if user has access to chat feature
    check_assoc_feature(request, "chat")

    # Build base context for the user
    context = get_context(request)

    # Add user's contacts ordered by last message timestamp
    context.update(
        {
            "list": Contact.objects.filter(me=request.user.member, assoc_id=context["association_id"]).order_by(
                "-last_message"
            )
        }
    )

    return render(request, "larpmanager/member/chats.html", context)


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
    context = get_member(n)
    yid = context["member"].id
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
    context["list"] = ChatMessage.objects.filter(channel=channel, assoc_id=request.assoc["id"]).order_by("-created")
    return render(request, "larpmanager/member/chat.html", context)


@login_required
def badges(request: HttpRequest) -> HttpResponse:
    """Display list of badges for the current association."""
    # Initialize context with user data and empty badges list
    context = get_context(request)
    context.update({"badges": []})

    # Verify user has permission to view badges feature
    check_assoc_feature(request, "badge")

    # Fetch and add badges to context, ordered by number
    for badge in Badge.objects.filter(assoc_id=context["association_id"]).order_by("number"):
        context["badges"].append(badge.show(request.LANGUAGE_CODE))

    # Set page identifier and render template
    context["page"] = "badges"
    return render(request, "larpmanager/general/badges.html", context)


@login_required
def badge(request: HttpRequest, n: str, p: int = 1) -> HttpResponse:
    """Display a badge with shuffled member list."""
    check_assoc_feature(request, "badge")
    badge = get_badge(n, request)

    # Initialize context with badge data
    context = get_context(request)
    context.update({"badge": badge.show(request.LANGUAGE_CODE), "list": []})

    # Collect all badge members
    for el in badge.members.all():
        context["list"].append(el)

    # Shuffle members using deterministic daily seed
    v = datetime.today().date() - date(1970, 1, 1)
    random.Random(v.days).shuffle(context["list"])

    return render(request, "larpmanager/general/badge.html", context)


@login_required
def leaderboard(request: HttpRequest, p: int = 1) -> HttpResponse:
    """Display paginated leaderboard of members with badge scores.

    This view renders a paginated leaderboard showing members ranked by their
    badge scores. Requires the 'badge' feature to be enabled for the association.

    Args:
        request: Django HTTP request object containing user and association data
        p: Page number for pagination, defaults to 1. Will be clamped to valid range.

    Returns:
        HttpResponse: Rendered leaderboard page with member rankings and pagination

    Raises:
        PermissionDenied: If the 'badge' feature is not enabled for the association
    """
    # Check if badge feature is enabled for the association
    check_assoc_feature(request, "badge")

    # Get sorted list of members with their badge scores
    context = get_context(request)
    member_list = get_leaderboard(context["association_id"])

    # Configure pagination settings
    num_el = 25
    num_pages = math.ceil(len(member_list) / num_el)

    # Normalize page number to valid range
    if p < 0:
        p = 1
    p = min(p, num_pages)

    # Build context with pagination data
    context.update(
        {
            "pages": member_list[(p - 1) * num_el : p * num_el],
            "num_pages": num_pages,
            "number": p,
            "previous_page_number": p - 1,
            "next_page_number": p + 1,
        }
    )

    # Set page identifier for template
    context["page"] = "leaderboard"
    return render(request, "larpmanager/general/leaderboard.html", context)


@login_required
def unsubscribe(request: HttpRequest) -> HttpResponse:
    """Unsubscribe user from newsletter communications.

    Args:
        request: HTTP request object containing user and association data

    Returns:
        Redirect response to home page
    """
    # Build context with user and association information
    context = get_context(request)
    context.update({"member": request.user.member, "association_id": context["association_id"]})

    # Get user membership and update newsletter preference
    mb = get_user_membership(context["member"], context["association_id"])
    mb.newsletter = NewsletterChoices.NO
    mb.save()

    # Show success message and redirect to home
    messages.success(request, _("The request of removal from further communication has been successfull!"))
    return redirect("home")


@login_required
def vote(request: HttpRequest) -> HttpResponse:
    """Handle voting functionality for association members.

    Manages voting processes, ballot submissions, and vote counting
    for association governance and decision-making.

    Args:
        request: The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Rendered voting page or redirect response.

    Raises:
        PermissionDenied: If user doesn't have voting feature access.
        ValidationError: If voting configuration is invalid.
    """
    # Verify user has access to voting feature
    check_assoc_feature(request, "vote")
    context = get_context(request)
    context.update({"member": request.user.member, "association_id": context["association_id"]})

    # Set current year for membership and voting validation
    context["year"] = datetime.now().year

    # Check if membership payment is required and completed
    if "membership" in request.assoc["features"]:
        que = AccountingItemMembership.objects.filter(assoc_id=context["association_id"], year=context["year"])
        if not que.filter(member_id=context["member"].id).exists():
            messages.error(request, _("You must complete payment of membership dues in order to vote!"))
            return redirect("acc_membership")

    # Check if user has already voted this year
    que = Vote.objects.filter(member=context["member"], assoc_id=context["association_id"], year=context["year"])
    if que.count() > 0:
        context["done"] = True
        return render(request, "larpmanager/member/vote.html", context)

    # Retrieve voting configuration from association settings
    assoc_id = context["association_id"]

    context["vote_open"] = get_assoc_config(assoc_id, "vote_open", False, context)
    context["vote_cands"] = get_assoc_config(assoc_id, "vote_candidates", "", context).split(",")
    context["vote_min"] = get_assoc_config(assoc_id, "vote_min", "1", context)
    context["vote_max"] = get_assoc_config(assoc_id, "vote_max", "1", context)

    # Process vote submission if POST request
    if request.method == "POST":
        cnt = 0
        # Iterate through candidate IDs and record votes
        for m_id in context["vote_cands"]:
            v = request.POST.get(f"vote_{m_id}")
            if not v:
                continue
            cnt += 1
            # Create vote record for each selected candidate
            Vote.objects.create(
                member=context["member"],
                assoc_id=context["association_id"],
                year=context["year"],
                number=cnt,
                candidate_id=m_id,
            )
        return redirect(request.path_info)

    # Build list of candidate objects for display
    context["candidates"] = []
    for mb in context["vote_cands"]:
        try:
            idx = int(mb)
            context["candidates"].append(Member.objects.get(pk=idx))
        except Exception:
            # Skip invalid candidate IDs
            pass

    # Randomize candidate order to prevent position bias
    random.shuffle(context["candidates"])

    return render(request, "larpmanager/member/vote.html", context)


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
    context = get_context(request)

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
        return render(request, "larpmanager/member/delegated.html", context)

    # Handle parent account managing delegated accounts
    # Retrieve all delegated child accounts for this parent
    context["list"] = Member.objects.filter(parent=request.user.member)
    del_dict = {el.id: el for el in context["list"]}

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
            mb = get_user_membership(user.member, context["association_id"])
            mb.compiled = True
            mb.save()

            messages.success(request, _("New delegate user added!"))
            return redirect("delegated")
    else:
        # Display form for creating new delegated account
        form = ProfileForm(request=request)

    context["form"] = form

    # Add accounting information for each delegated account
    for el in context["list"]:
        del_ctx = {"member": el, "association_id": context["association_id"]}
        info_accounting(request, del_ctx)
        el.context = del_ctx
    return render(request, "larpmanager/member/delegated.html", context)


def get_user_backend():
    authentication_backend = "allauth.account.auth_backends.AuthenticationBackend"
    return authentication_backend


@login_required
def registrations(request: HttpRequest) -> HttpResponse:
    """
    Display user's registrations with status information.

    Retrieves and displays all registrations for the current user within their
    association, including status information and related data for optimization.

    Args:
        request (HttpRequest): The HTTP request object containing user and
            association information.

    Returns:
        HttpResponse: Rendered template displaying the user's registrations
            with status and related information.
    """
    nt = []
    context = get_context(request)

    # Get user's registrations filtered by association for caching optimization
    my_regs = Registration.objects.filter(member=request.user.member, run__event_id=context["association_id"])
    my_regs_dict = {reg.run_id: reg for reg in my_regs}

    # Prepare context data
    context.update(
        {
            "pre_registrations_dict": get_pre_registrations_dict(context["association_id"], request.user.member),
            "character_rels_dict": get_character_rels_dict(my_regs_dict, request.user.member),
            "payment_invoices_dict": get_payment_invoices_dict(my_regs_dict, request.user.member),
        }
    )

    # Process each registration to calculate status and append to results
    for reg in my_regs:
        # Calculate registration status
        registration_status(reg.run, request.user, context)
        nt.append(reg)

    # Render template with processed registration list
    context["registration_list"] = nt
    return render(request, "larpmanager/member/registrations.html", context)
