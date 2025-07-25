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

from django.conf import settings as conf_settings
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path

from larpmanager.forms.member import (
    MyPasswordResetConfirmForm,
    MyPasswordResetForm,
    MyRegistrationFormUniqueEmail,
)
from larpmanager.views import auth as views_auth
from larpmanager.views import base as views_base
from larpmanager.views.base import MyLoginView
from larpmanager.views.user import accounting as views_ua
from larpmanager.views.user import casting as views_uca
from larpmanager.views.user import character as views_uc
from larpmanager.views.user import event as views_ue
from larpmanager.views.user import member as views_um
from larpmanager.views.user import miscellanea as views_ums
from larpmanager.views.user import pdf as views_up
from larpmanager.views.user import registration as views_ur

urlpatterns = [
    path(
        "",
        views_base.home,
        name="home",
    ),
    path(
        "share/",
        views_ue.share,
        name="share",
    ),
    path(
        "legal_notice/",
        views_ue.legal_notice,
        name="legal_notice",
    ),
    path(
        "home/<slug:lang>/",
        views_base.home,
        name="home",
    ),
    path(
        "carousel/",
        views_ue.carousel,
        name="carousel",
    ),
    path(
        "calendar/past/",
        views_ue.calendar_past,
        name="calendar_past",
    ),
    path(
        "help/",
        views_ums.help,
        name="help",
    ),
    path(
        "help/<int:n>/",
        views_ums.help_red,
        name="help_red",
    ),
    path(
        "help/attachment/<int:p>/",
        views_ums.help_attachment,
        name="help_attachment",
    ),
    path(
        "home/json/",
        views_ue.home_json,
        name="home_json",
    ),
    path(
        "home/json/<slug:lang>/",
        views_ue.home_json,
        name="home_json",
    ),
    path(
        "language/",
        views_um.language,
        name="language",
    ),
    path(
        "profile/",
        views_um.profile,
        name="profile",
    ),
    path(
        "profile/upload/",
        views_um.profile_upload,
        name="profile_upload",
    ),
    path(
        "profile/rotate/<int:n>/",
        views_um.profile_rotate,
        name="profile_rotate",
    ),
    path(
        "profile/privacy/",
        views_um.profile_privacy,
        name="profile_privacy",
    ),
    path(
        "profile/privacy/rewoke/<slug:slug>/",
        views_um.profile_privacy_rewoke,
        name="profile_privacy_rewoke",
    ),
    path(
        "pre_register/",
        views_ur.pre_register,
        name="pre_register",
    ),
    path(
        "pre_register/<slug:s>/remove",
        views_ur.pre_register_remove,
        name="pre_register_remove",
    ),
    path(
        "registrations/",
        views_um.registrations,
        name="registrations",
    ),
    path(
        "membership/",
        views_um.membership,
        name="membership",
    ),
    path(
        "membership/request/",
        views_um.membership_request,
        name="membership_request",
    ),
    path(
        "membership/request/test",
        views_um.membership_request_test,
        name="membership_request_test",
    ),
    path(
        "public/<int:n>/",
        views_um.public,
        name="public",
    ),
    path(
        "badges/",
        views_um.badges,
        name="badges",
    ),
    path(
        "leaderboard/",
        views_um.leaderboard,
        name="leaderboard",
    ),
    path(
        "leaderboard/<int:p>/",
        views_um.leaderboard,
        name="leaderboard",
    ),
    path(
        "badge/<int:n>/",
        views_um.badge,
        name="badge",
    ),
    path(
        "badge/<int:n>/<int:p>/",
        views_um.badge,
        name="badge",
    ),
    path(
        "chats/",
        views_um.chats,
        name="chats",
    ),
    path(
        "chat/<int:n>/",
        views_um.chat,
        name="chat",
    ),
    path(
        "vote/",
        views_um.vote,
        name="vote",
    ),
    path(
        "unsubscribe/",
        views_um.unsubscribe,
        name="unsubscribe",
    ),
    path(
        "delegated/",
        views_um.delegated,
        name="delegated",
    ),
    path(
        "accounting/",
        views_ua.accounting,
        name="accounting",
    ),
    path(
        "accounting/pay/<slug:s>/<int:n>/",
        views_ua.acc_pay,
        name="acc_pay",
    ),
    path(
        "accounting/pay/<slug:s>/<int:n>/<slug:method>/",
        views_ua.acc_pay,
        name="acc_pay",
    ),
    path(
        "accounting/registration/<int:reg_id>/",
        views_ua.acc_reg,
        name="acc_reg",
    ),
    path(
        "accounting/registration/<int:reg_id>/<slug:method>/",
        views_ua.acc_reg,
        name="acc_reg",
    ),
    path(
        "accounting/membership/",
        views_ua.acc_membership,
        name="acc_membership",
    ),
    path(
        "accounting/membership/<slug:method>/",
        views_ua.acc_membership,
        name="acc_membership",
    ),
    path(
        "accounting/donate/",
        views_ua.acc_donate,
        name="acc_donate",
    ),
    path(
        "accounting/refund/",
        views_ua.acc_refund,
        name="acc_refund",
    ),
    path(
        "accounting/cancelled/",
        views_ua.acc_cancelled,
        name="acc_cancelled",
    ),
    path(
        "accounting/payed/<int:p>/",
        views_ua.acc_payed,
        name="acc_payed",
    ),
    path(
        "accounting/wait/",
        views_ua.acc_wait,
        name="acc_wait",
    ),
    path(
        "accounting/webhook/paypal/",
        views_ua.acc_webhook_paypal,
        name="acc_webhook_paypal",
    ),
    path(
        "accounting/webhook/paypal/<slug:s>/",
        views_ua.acc_webhook_paypal,
        name="acc_webhook_paypal",
    ),
    path(
        "accounting/webhook/satispay",
        views_ua.acc_webhook_satispay,
        name="acc_webhook_satispay",
    ),
    path(
        "accounting/webhook/stripe",
        views_ua.acc_webhook_stripe,
        name="acc_webhook_stripe",
    ),
    path(
        "accounting/stripe_confirm",
        views_ua.acc_webhook_stripe,
        name="acc_webhook_stripe",
    ),
    path(
        "accounting/webhook/sumup",
        views_ua.acc_webhook_sumup,
        name="acc_webhook_sumup",
    ),
    path(
        "accounting/webhook/redsys/",
        views_ua.acc_webhook_redsys,
        name="acc_webhook_redsys",
    ),
    path(
        "accounting/redsys/ko",
        views_ua.acc_redsys_ko,
        name="acc_redsys_ko",
    ),
    path(
        "accounting/credits/",
        views_ua.accounting_credits,
        name="accounting_credits",
    ),
    path(
        "accounting/tokens/",
        views_ua.accounting_tokens,
        name="accounting_tokens",
    ),
    path(
        "accounting/collection/",
        views_ua.acc_collection,
        name="acc_collection",
    ),
    path(
        "accounting/collection/<slug:s>/",
        views_ua.acc_collection_manage,
        name="acc_collection_manage",
    ),
    path(
        "accounting/collection/<slug:s>/participate/",
        views_ua.acc_collection_participate,
        name="acc_collection_participate",
    ),
    path(
        "accounting/collection/<slug:s>/close/",
        views_ua.acc_collection_close,
        name="acc_collection_close",
    ),
    path(
        "accounting/collection/<slug:s>/redeem/",
        views_ua.acc_collection_redeem,
        name="acc_collection_redeem",
    ),
    path(
        "accounting/submit/<slug:s>/<path:p>/",
        views_ua.acc_submit,
        name="acc_submit",
    ),
    path(
        "accounting/confirm/<slug:c>/",
        views_ua.acc_confirm,
        name="acc_confirm",
    ),
    path(
        "shuttle/",
        views_ums.shuttle,
        name="shuttle",
    ),
    path(
        "shuttle/new/",
        views_ums.shuttle_new,
        name="shuttle_new",
    ),
    path(
        "shuttle/edit/<int:n>/",
        views_ums.shuttle_edit,
        name="shuttle_edit",
    ),
    re_path(
        r"^paypal/",
        include("paypal.standard.ipn.urls"),
    ),
    path(
        "<slug:s>/<int:n>/",
        views_ue.gallery,
        name="gallery",
    ),
    path(
        "<slug:s>/<int:n>/event/",
        views_ue.event,
        name="event",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/",
        views_uc.character,
        name="character",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/change/",
        views_uc.character_edit,
        name="character_change",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/customize/",
        views_uc.character_customize,
        name="character_customize",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/profile/rotate/<int:r>/",
        views_uc.character_profile_rotate,
        name="character_profile_rotate",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/profile/upload/",
        views_uc.character_profile_upload,
        name="character_profile_upload",
    ),
    path(
        "<slug:s>/<int:n>/character/list/",
        views_uc.character_list,
        name="character_list",
    ),
    path(
        "<slug:s>/<int:n>/character/create/",
        views_uc.character_create,
        name="character_create",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/abilities/",
        views_uc.character_abilities,
        name="character_abilities",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/assign/",
        views_uc.character_assign,
        name="character_assign",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/relationships/",
        views_uc.character_relationships,
        name="character_relationships",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/relationships/edit/<int:oth>",
        views_uc.character_relationships_edit,
        name="character_relationships_edit",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/pdf/sheet/",
        views_up.character_pdf_sheet,
        name="character_pdf_sheet",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/pdf/friendly/",
        views_up.character_pdf_sheet_friendly,
        name="character_pdf_sheet_friendly",
    ),
    path(
        "<slug:s>/<int:n>/character/<int:num>/pdf/relationships/",
        views_up.character_pdf_relationships,
        name="character_pdf_relationships",
    ),
    path(
        "<slug:s>/<int:n>/character/your/",
        views_uc.character_your,
        name="character_your",
    ),
    path(
        "<slug:s>/<int:n>/character/your/<path:p>",
        views_uc.character_your,
        name="character_your",
    ),
    path(
        "<slug:s>/<int:n>/search/",
        views_ue.search,
        name="search",
    ),
    path(
        "<slug:s>/<int:n>/limitations/",
        views_ue.limitations,
        name="limitations",
    ),
    path(
        "<slug:s>/<int:n>/gift/",
        views_ur.gift,
        name="gift",
    ),
    path(
        "<slug:s>/<int:n>/gift/edit/<int:r>/",
        views_ur.gift_edit,
        name="gift_edit",
    ),
    path(
        "<slug:s>/<int:n>/gift/redeem/<slug:code>/",
        views_ur.gift_redeem,
        name="gift_redeem",
    ),
    path(
        "<slug:s>/<int:n>/casting/",
        views_uca.casting,
        name="casting",
    ),
    path(
        "<slug:s>/<int:n>/casting/<int:typ>/",
        views_uca.casting,
        name="casting",
    ),
    path(
        "<slug:s>/<int:n>/casting/preferences/",
        views_uca.casting_preferences,
        name="casting_preferences",
    ),
    path(
        "<slug:s>/<int:n>/casting/preferences/<int:typ>/",
        views_uca.casting_preferences,
        name="casting_preferences",
    ),
    path(
        "<slug:s>/<int:n>/casting/history/",
        views_uca.casting_history,
        name="casting_history",
    ),
    path(
        "<slug:s>/<int:n>/casting/history/<int:typ>/",
        views_uca.casting_history,
        name="casting_history",
    ),
    path(
        "<slug:s>/<int:n>/factions/",
        views_ue.factions,
        name="factions",
    ),
    path(
        "<slug:s>/<int:n>/faction/<int:g>/",
        views_ue.faction,
        name="faction",
    ),
    path(
        "<slug:s>/<int:n>/quests/",
        views_ue.quests,
        name="quests",
    ),
    path(
        "<slug:s>/<int:n>/quests/<int:g>/",
        views_ue.quests,
        name="quests",
    ),
    path(
        "<slug:s>/<int:n>/quest/<int:g>/",
        views_ue.quest,
        name="quest",
    ),
    path(
        "<slug:s>/<int:n>/album/",
        views_ums.album,
        name="album",
    ),
    path(
        "<slug:s>/<int:n>/album/<int:num>/",
        views_ums.album_sub,
        name="album_sub",
    ),
    path(
        "<slug:s>/export/<slug:t>/",
        views_ue.export,
        name="export",
    ),
    path(
        "<slug:s>/<int:n>/handout/<slug:cod>/",
        views_ums.handout_ext,
        name="handout_ext",
    ),
    path(
        "<slug:s>/<int:n>/portraits/",
        views_up.portraits,
        name="portraits",
    ),
    path(
        "<slug:s>/<int:n>/profiles/",
        views_up.profiles,
        name="profiles",
    ),
    path(
        "<slug:s>/<int:n>/register/",
        views_ur.register,
        name="register",
    ),
    path(
        "<slug:s>/<int:n>/register/discount/<slug:dis>/",
        views_ur.register,
        name="register",
    ),
    path(
        "<slug:s>/<int:n>/register/ticket/<int:tk>/",
        views_ur.register,
        name="register",
    ),
    path(
        "<slug:s>/<int:n>/register/reduced/",
        views_ur.register_reduced,
        name="register_reduced",
    ),
    path(
        "<slug:s>/<int:n>/register/<slug:sc>/",
        views_ur.register_exclusive,
        name="register_exclusive",
    ),
    path(
        "<slug:s>/<int:n>/register/<slug:sc>/discount/<slug:dis>/",
        views_ur.register_exclusive,
        name="register_exclusive",
    ),
    path(
        "<slug:s>/<int:n>/discount/",
        views_ur.discount,
        name="discount",
    ),
    path(
        "<slug:s>/<int:n>/discount/list",
        views_ur.discount_list,
        name="discount_list",
    ),
    path(
        "<slug:s>/<int:n>/unregister/",
        views_ur.unregister,
        name="unregister",
    ),
    path(
        "<slug:s>/<int:n>/workshops/",
        views_ums.workshops,
        name="workshops",
    ),
    path(
        "<slug:s>/<int:n>/workshops/answer/<int:m>/",
        views_ums.workshop_answer,
        name="workshop_answer",
    ),
    path(
        "<slug:s>/<int:n>/help/",
        views_ums.help,
        name="help",
    ),
    path(
        "<slug:s>/<int:n>/show_char/",
        views_uc.show_char,
        name="show_char",
    ),
    path(
        "register/conditions/",
        views_ur.register_conditions,
        name="register_conditions",
    ),
    path(
        "at/<slug:s>/",
        views_ums.url_short,
        name="url_short",
    ),
    path(
        "<slug:s>/register/",
        views_ue.event_register,
        name="event_register",
    ),
    path(
        "<slug:s>/register/pre/",
        views_ur.pre_register,
        name="pre_register",
    ),
    path(
        "<slug:s>/register/conditions/",
        views_ur.register_conditions,
        name="register_conditions",
    ),
    path(
        "util/<slug:cod>/",
        views_ums.util,
        name="util",
    ),
    path(
        "register/",
        views_auth.MyRegistrationView.as_view(
            form_class=MyRegistrationFormUniqueEmail,
            success_url="/",
        ),
        name="registration_register",
    ),
    path("login/", MyLoginView.as_view(), name="login"),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page=conf_settings.LOGOUT_REDIRECT_URL),
        name="logout",
    ),
    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(form_class=MyPasswordResetForm),
        name="password_reset",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views_auth.MyPasswordResetConfirmView.as_view(form_class=MyPasswordResetConfirmForm),
        name="password_reset_confirm",
    ),
    path(
        "after_login/<slug:subdomain>/",
        views_base.after_login,
        name="after_login",
    ),
    path(
        "after_login/<slug:subdomain>/<path:path>",
        views_base.after_login,
        name="after_login",
    ),
    path(
        "tutorial_query/",
        views_base.tutorial_query,
        name="tutorial_query",
    ),
    path("upload_image/", views_base.upload_image, name="upload_image"),
]
