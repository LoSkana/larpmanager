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

import re
import traceback
from functools import wraps
from time import sleep

from background_task import background
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.models.association import Association, AssocText, get_url
from larpmanager.models.event import Event
from larpmanager.models.member import Member
from larpmanager.models.miscellanea import Email
from larpmanager.utils.text import get_assoc_text

INTERNAL_KWARGS = {"schedule", "repeat", "repeat_until", "remove_existing_tasks"}


def background_auto(schedule=0, **background_kwargs):
    def decorator(func):
        task = background(schedule=schedule, **background_kwargs)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if getattr(conf_settings, "AUTO_BACKGROUND_TASKS", False):
                clean_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}
                return func(*args, **clean_kwargs)
            else:
                return task(*args, **kwargs)

        wrapper.task = task
        wrapper.task_function = func
        return wrapper

    return decorator


# MAIL


def mail_error(subj, body, e=None):
    print("mail error")
    print(subj)
    print(body)
    print(e)
    if e:
        body = f"{traceback.format_exc()} <br /><br /> {subj} <br /><br /> {body}"
    else:
        body = f"{subj} <br /><br /> {body}"
    subj = "[LarpManager] Mail error"
    for _name, email in conf_settings.ADMINS:
        my_send_simple_mail(subj, body, email)


@background_auto()
def send_mail_exec(players, subj, body, obj_id=None, reply_to=None):
    aux = {}

    if obj_id:
        obj = Association.objects.filter(pk=obj_id).first() or Event.objects.filter(pk=obj_id).first()
        if not obj:
            return
        subj = f"[{obj.name}] {subj}"

    cnt = 0
    for email in players.split(","):
        if not email:
            continue
        if email in aux:
            continue
        cnt += 1
        # noinspection PyUnboundLocalVariable
        my_send_mail(subj, body, email.strip(), obj, reply_to, schedule=cnt * 10)
        aux[email] = 1


def remove_html_tags(text):
    html_pattern = re.compile("<.*?>")
    clean_text = re.sub(html_pattern, "", text)
    return clean_text


@background_auto(queue="mail")
def my_send_mail_bkg(email_pk):
    email = Email.objects.get(pk=email_pk)
    if email.sent:
        print("email already sent!")
        return

    my_send_simple_mail(email.subj, email.body, email.recipient,
        email.assoc_id, email.event_id, email.reply_to)

    email.sent = timezone.now()
    email.save()


def send_email_lock(sender_email):
    # wait for lock
    lock_key = f"mail-lock-{sender_email}"
    lock_expiration = 10
    while not cache.add(lock_key, True, lock_expiration):
        sleep(1)


def my_send_simple_mail(subj, body, m_email, assoc_id=None, event_id=None, reply_to=None):
    hdr = {}
    bcc = []

    connection = None
    sender_email = "info@larpmanager.com"
    sender = f"LarpManager <{sender_email}>"
    event_settings = False

    try:
        # Event confs: to apply only if email params are set up
        if event_id:
            event = Event.objects.get(pk=event_id)
            email_host_user = event.get_feature_conf("mail_server_host_user", "")
            if email_host_user:
                sender_email = email_host_user
                sender = f"{event.name.replace(':', ' ')} <{sender_email}>"
                send_email_lock(sender_email)
                connection = get_connection(
                    host=event.get_feature_conf("mail_server_host", ""),
                    port=event.get_feature_conf("mail_server_port", ""),
                    username=event.get_feature_conf("mail_server_host_user", ""),
                    password=event.get_feature_conf("mail_server_host_password", ""),
                    use_tls=event.get_feature_conf("mail_server_use_tls", False),
                )
                event_settings = True

        # Assoc confs: to apply
        if assoc_id:
            assoc = Association.objects.get(pk=assoc_id)
            if assoc.get_feature_conf("mail_cc", False):
                bcc.append(assoc.main_mail)

            # See if we have to apply custom mail settings
            email_host_user = assoc.get_feature_conf("mail_server_host_user", "")
            if email_host_user:
                if not event_settings:
                    sender_email = email_host_user
                    sender = f"{assoc.name} <{sender_email}>"
                    send_email_lock(sender_email)
                    connection = get_connection(
                        host=assoc.get_feature_conf("mail_server_host", ""),
                        port=assoc.get_feature_conf("mail_server_port", ""),
                        username=assoc.get_feature_conf("mail_server_host_user", ""),
                        password=assoc.get_feature_conf("mail_server_host_password", ""),
                        use_tls=assoc.get_feature_conf("mail_server_use_tls", False),
                    )
            # See if we apply standard mail settings (if no event custom settings)
            else:
                if not event_settings:
                    sender_email = f"{assoc.slug}@larpmanager.com"
                    sender = f"{assoc.name} <{sender_email}>"

        if not connection:
            send_email_lock(sender_email)
            connection = get_connection()

        if reply_to:
            hdr["Reply-To"] = reply_to

        hdr["List-Unsubscribe"] = f"<mailto:{sender_email}>"

        body_html = body

        # pprint(connection)
        email = EmailMultiAlternatives(
            subj,
            remove_html_tags(body),
            sender,
            [m_email],
            bcc=bcc,
            headers=hdr,
            connection=connection,
        )
        email.attach_alternative(body_html, "text/html")
        email.send()

        if conf_settings.DEBUG:
            print(m_email)
            print(subj)
            print(body)

    except Exception as e:
        mail_error(subj, body, e)
        raise e


def add_unsubscribe_body(assoc):
    txt = "<br /><br />======================"
    txt += "<br /><br />" + _(
        "Do you want to unsubscribe from our communication lists? <a href='%(url)s'>Unsubscribe</a>"
    ) % {"url": get_url("unsubscribe", assoc)}
    return txt


def my_send_mail(subj, body, recipient, obj=None, reply_to=None, schedule=0):
    subj = subj.replace("  ", " ")

    event_id = None
    if isinstance(obj, Event):
        event_id = obj.id  # type: ignore[attr-defined]

    assoc_id = None
    if isinstance(obj, Association):
        assoc_id = obj.id  # type: ignore[attr-defined]
    elif obj is not None:
        assoc_id = obj.assoc_id  # type: ignore[attr-defined]

    if assoc_id:
        sign = get_assoc_text(assoc_id, AssocText.SIGNATURE)
        if sign:
            body += sign

    body += add_unsubscribe_body(obj)

    if isinstance(recipient, Member):
        recipient = recipient.email

    # print(assoc)

    subj_str = str(subj)
    body_str = str(body)

    email = Email.objects.create(
        assoc_id=assoc_id,
        event_id=event_id,
        recipient=recipient,
        subj=subj_str,
        body_str=body_str,
        reply_to=reply_to
    )

    my_send_mail_bkg(email.pk, schedule=schedule)
