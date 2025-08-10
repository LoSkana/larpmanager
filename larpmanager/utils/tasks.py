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

from background_task import background
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.text_fields import remove_html_tags
from larpmanager.models.association import Association, AssocTextType, get_url
from larpmanager.models.event import Event, Run
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
def send_mail_exec(players, subj, body, assoc_id=None, run_id=None, reply_to=None):
    aux = {}

    if assoc_id:
        obj = Association.objects.filter(pk=assoc_id).first()
    elif run_id:
        obj = Run.objects.filter(pk=run_id).first()
    else:
        print(f"obj not found! {assoc_id} {run_id}")
        return

    subj = f"[{obj}] {subj}"

    recipients = players.split(",")

    notify_admins(f"Sending {len(recipients)} - [{obj}]", f"{subj}")

    cnt = 0
    for email in recipients:
        if not email:
            continue
        if email in aux:
            continue
        cnt += 1
        # noinspection PyUnboundLocalVariable
        my_send_mail(subj, body, email.strip(), obj, reply_to, schedule=cnt * 10)
        aux[email] = 1


@background_auto(queue="mail")
def my_send_mail_bkg(email_pk):
    try:
        email = Email.objects.get(pk=email_pk)
    except ObjectDoesNotExist:
        return

    if email.sent:
        print("email already sent!")
        return

    my_send_simple_mail(email.subj, email.body, email.recipient, email.assoc_id, email.run_id, email.reply_to)

    email.sent = timezone.now()
    email.save()


def clean_sender(name):
    name = name.replace(":", " ")
    name = name.split(",")[0]
    name = re.sub(r"[^a-zA-Z0-9\s\-\']", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def my_send_simple_mail(subj, body, m_email, assoc_id=None, run_id=None, reply_to=None):
    hdr = {}
    bcc = []

    connection = None
    sender_email = "info@larpmanager.com"
    sender = f"LarpManager <{sender_email}>"
    event_settings = False

    try:
        # Event confs: to apply only if email params are set up
        if run_id:
            run = Run.objects.get(pk=run_id)
            event = run.event
            email_host_user = event.get_config("mail_server_host_user", "")
            if email_host_user:
                sender_email = email_host_user
                sender = f"{clean_sender(event.name)} <{sender_email}>"
                connection = get_connection(
                    host=event.get_config("mail_server_host", ""),
                    port=event.get_config("mail_server_port", ""),
                    username=event.get_config("mail_server_host_user", ""),
                    password=event.get_config("mail_server_host_password", ""),
                    use_tls=event.get_config("mail_server_use_tls", False),
                )
                event_settings = True

        # Assoc confs: to apply
        if assoc_id:
            assoc = Association.objects.get(pk=assoc_id)
            if assoc.get_config("mail_cc", False) and assoc.main_mail:
                bcc.append(assoc.main_mail)

            # See if we have to apply custom mail settings
            email_host_user = assoc.get_config("mail_server_host_user", "")
            if email_host_user:
                if not event_settings:
                    sender_email = email_host_user
                    sender = f"{clean_sender(assoc.name)} <{sender_email}>"
                    connection = get_connection(
                        host=assoc.get_config("mail_server_host", ""),
                        port=assoc.get_config("mail_server_port", ""),
                        username=assoc.get_config("mail_server_host_user", ""),
                        password=assoc.get_config("mail_server_host_password", ""),
                        use_tls=assoc.get_config("mail_server_use_tls", False),
                    )
            # See if we apply standard mail settings (if no event custom settings)
            elif not event_settings:
                sender_email = f"{assoc.slug}@larpmanager.com"
                sender = f"{clean_sender(assoc.name)} <{sender_email}>"

        if not connection:
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

    run_id = None
    assoc_id = None
    if obj:
        if isinstance(obj, Run):
            run_id = obj.id  # type: ignore[attr-defined]
            assoc_id = obj.event.assoc_id  # type: ignore[attr-defined]
        if isinstance(obj, Event):
            assoc_id = obj.assoc_id  # type: ignore[attr-defined]
        elif isinstance(obj, Association):
            assoc_id = obj.id  # type: ignore[attr-defined]
        elif hasattr(obj, "run_id") and obj.run_id:
            run_id = obj.run_id
            assoc_id = obj.run.event.assoc_id
        elif hasattr(obj, "assoc_id") and obj.assoc_id:
            assoc_id = obj.assoc_id
        elif hasattr(obj, "event_id") and obj.event_id:
            assoc_id = obj.event.assoc_id

        if assoc_id:
            sign = get_assoc_text(assoc_id, AssocTextType.SIGNATURE)
            if sign:
                body += sign

    body += add_unsubscribe_body(obj)

    if isinstance(recipient, Member):
        recipient = recipient.email

    # print(assoc)

    subj_str = str(subj)
    body_str = str(body)

    email = Email.objects.create(
        assoc_id=assoc_id, run_id=run_id, recipient=recipient, subj=subj_str, body=body_str, reply_to=reply_to
    )

    my_send_mail_bkg(email.pk, schedule=schedule)


def notify_admins(subj, text, exception=None):
    if exception:
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        text += "\n" + tb
    for _name, email in conf_settings.ADMINS:
        my_send_mail(subj, text, email)
