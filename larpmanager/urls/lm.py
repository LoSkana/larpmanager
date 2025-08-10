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

from django.urls import (
    path,
)

from larpmanager.views import larpmanager as views_lm

urlpatterns = [
    path(
        "join/",
        views_lm.join,
        name="join",
    ),
    path(
        "discover/",
        views_lm.discover,
        name="discover",
    ),
    path(
        "tutorials/",
        views_lm.tutorials,
        name="tutorials",
    ),
    path(
        "tutorials/<slug:slug>/",
        views_lm.tutorials,
        name="tutorials",
    ),
    path(
        "usage/",
        views_lm.usage,
        name="usage",
    ),
    path(
        "demo/",
        views_lm.demo,
        name="demo",
    ),
    path(
        "about-us/",
        views_lm.about_us,
        name="about_us",
    ),
    path(
        "privacy/",
        views_lm.privacy,
        name="privacy",
    ),
    path(
        "contact/",
        views_lm.contact,
        name="contact",
    ),
    path(
        "blog/",
        views_lm.blog,
        name="blog",
    ),
    path(
        "blog/<slug:slug>",
        views_lm.blog,
        name="blog",
    ),
    path(
        "lm/list/",
        views_lm.lm_list,
        name="lm_list",
    ),
    path(
        "lm/payments/",
        views_lm.lm_payments,
        name="lm_payments",
    ),
    path(
        "lm/payments/<int:r>",
        views_lm.lm_payments_confirm,
        name="lm_payments_confirm",
    ),
    path(
        "lm/send/",
        views_lm.lm_send,
        name="lm_send",
    ),
    path(
        "lm/profile/",
        views_lm.lm_profile,
        name="lm_profile",
    ),
    path(
        "lm/profile/<slug:func>",
        views_lm.lm_profile_rm,
        name="lm_profile_rm",
    ),
    path(
        "redirect/<path:p>",
        views_lm.redr,
        name="redr",
    ),
    path(
        "activate/<slug:cod>/next/<path:p>",
        views_lm.activate_feature_assoc,
        name="activate_feature_assoc",
    ),
    path(
        "activate/<slug:cod>/",
        views_lm.activate_feature_assoc,
        name="activate_feature_assoc",
    ),
    path(
        "<slug:s>/<int:n>/activate/<slug:cod>/next/<path:p>",
        views_lm.activate_feature_event,
        name="activate_feature_event",
    ),
    path(
        "<slug:s>/<int:n>/activate/<slug:cod>/",
        views_lm.activate_feature_event,
        name="activate_feature_event",
    ),
    path(
        "toggle_sidebar/",
        views_lm.toggle_sidebar,
        name="toggle_sidebar",
    ),
    path(
        "discord/",
        views_lm.discord,
        name="discord",
    ),
    path(
        "donate/",
        views_lm.donate,
        name="donate",
    ),
    path(
        "ticket/",
        views_lm.ticket,
        name="ticket",
    ),
    path(
        "ticket/<slug:s>/",
        views_lm.ticket,
        name="ticket",
    ),
    path(
        "debug/mail/",
        views_lm.debug_mail,
        name="debug_mail",
    ),
    path(
        "debug/",
        views_lm.debug_slug,
        name="debug_slug",
    ),
    path(
        "debug/<slug:s>/",
        views_lm.debug_slug,
        name="debug_slug",
    ),
    path(
        "debug/user/<int:s>/",
        views_lm.debug_user,
        name="debug_user",
    ),
]
