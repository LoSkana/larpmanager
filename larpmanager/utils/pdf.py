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

import os.path
import re
import shutil
import time
from datetime import datetime, timedelta, timezone

import lxml.etree
import pdfkit
from django.conf import settings as conf_settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _
from xhtml2pdf import pisa

from larpmanager.cache.association import get_cache_assoc
from larpmanager.cache.character import get_event_cache_all
from larpmanager.models.association import AssocTextType
from larpmanager.models.casting import AssignmentTrait, Casting, Trait
from larpmanager.models.miscellanea import PlayerRelationship, Util
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Faction,
    Handout,
    HandoutTemplate,
    Relationship,
)
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.common import (
    get_handout,
)
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import NotFoundError
from larpmanager.utils.tasks import background_auto
from larpmanager.utils.text import get_assoc_text


def fix_filename(s):
    return re.sub(r"[^A-Za-z0-9 ]+", "", s)


# reprint if file not exists, older than 1 day, or debug
def reprint(fp):
    if conf_settings.DEBUG:
        return True

    if not os.path.isfile(fp):
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    mtime = datetime.fromtimestamp(os.path.getmtime(fp), timezone.utc)
    return mtime < cutoff


def return_pdf(fp, fn):
    try:
        f = open(fp, "rb")
        response = HttpResponse(f.read(), content_type="application/pdf")
        f.close()
        response["Content-Disposition"] = f"inline;filename={fix_filename(fn)}.pdf"
        return response
    except FileNotFoundError as err:
        raise Http404("File not found") from err


def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources. Raises an exception if the file doesn't exist.
    """
    s_url = conf_settings.STATIC_URL
    s_root = conf_settings.STATIC_ROOT
    m_url = conf_settings.MEDIA_URL
    m_root = conf_settings.MEDIA_ROOT

    if uri.startswith(m_url):
        path = os.path.join(m_root, uri.replace(m_url, ""))
    elif uri.startswith(s_url):
        path = os.path.join(s_root, uri.replace(s_url, ""))
    else:
        return ""

    if not os.path.isfile(path):
        return ""

    return path


def add_pdf_instructions(ctx):
    for instr in ["page_css", "header_content", "footer_content"]:
        ctx[instr] = ctx["event"].get_config(instr, "")

    codes = {
        "<pdf:organization>": ctx["event"].assoc.name,
        "<pdf:event>": ctx["event"].name,
    }
    for m in ["number", "name", "title"]:
        codes[f"<pdf:{m}>"] = str(ctx["sheet_char"][m])

    # replace char infos
    for s in ["header_content", "footer_content"]:
        if s not in ctx:
            continue
        for el, value in codes.items():
            if el not in ctx[s]:
                continue
            ctx[s] = ctx[s].replace(el, value)

    # replace utils by code
    for s in ["header_content", "footer_content", "page_css"]:
        if s not in ctx:
            continue
        for x in re.findall(r"(#[\w-]+#)", ctx[s]):
            cod = x.replace("#", "")
            util = get_object_or_404(Util, cod=cod)
            ctx[s] = ctx[s].replace(x, util.util.url)
        # print(ctx['page_css'])


def xhtml_pdf(context, template_path, output_filename):
    template = get_template(template_path)

    html = template.render(context)

    with open(output_filename, "wb") as result_file:
        # create a pdf
        result = pisa.CreatePDF(html, dest=result_file, link_callback=link_callback)

        # check result
        if result.err:
            raise Http404("We had some errors <pre>" + html + "</pre>")


def pdf_template(ctx, tmp, out, small=False, html=False):
    if small:
        options = {
            "page-size": "A4",
            "margin-top": "0.1in",
            "margin-right": "0.1in",
            "margin-bottom": "0.1in",
            "margin-left": "0.1in",
            "encoding": "UTF-8",
            "custom-header": [("Accept-Encoding", "gzip")],
            # 'no-outline': None,
            "quiet": "",
        }
    else:
        options = {
            "page-size": "A4",
            "margin-top": "0.6in",
            "margin-right": "0.6in",
            "margin-bottom": "0.4in",
            "margin-left": "0.4in",
            "encoding": "UTF-8",
            "custom-header": [("Accept-Encoding", "gzip")],
            # 'no-outline': None,
            "quiet": "",
        }

    try:
        if html:
            t = Template(tmp)
            c = Context(ctx)
            html = t.render(c)
        else:
            template = get_template(tmp)
            html = template.render(ctx)
            # print(html)
        # html = html.replace(conf_settings.STATIC_URL, request.build_absolute_uri(conf_settings.STATIC_URL))
        # html = html.replace(conf_settings.MEDIA_URL, request.build_absolute_uri(conf_settings.MEDIA_URL))
        pdfkit.from_string(html, out, options)
    except Exception as e:
        print(e)


# ##print


def get_membership_request(ctx):
    fp = ctx["member"].get_request_filepath()
    temp_ctx = {"member": ctx["member"]}
    template = get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP)
    pdf_template(temp_ctx, template, fp, html=True)
    return return_pdf(fp, _("Membership registration of %(user)s") % {"user": ctx["member"]})


def print_character(ctx, force=False):
    fp = ctx["character"].get_sheet_filepath(ctx["run"])
    ctx["pdf"] = True
    if force or reprint(fp):
        get_character_sheet(ctx)
        add_pdf_instructions(ctx)
        xhtml_pdf(ctx, "pdf/sheets/auxiliary.html", fp)
    return return_pdf(fp, f"{ctx['character']}")


def print_character_friendly(ctx, force=False):
    fp = ctx["character"].get_sheet_friendly_filepath(ctx["run"])
    ctx["pdf"] = True
    if force or reprint(fp):
        get_character_sheet(ctx)
        pdf_template(ctx, "pdf/sheets/friendly.html", fp, True)
    return return_pdf(fp, f"{ctx['character']} - " + _("Lightweight"))


def print_character_rel(ctx, force=False):
    fp = ctx["character"].get_relationships_filepath(ctx["run"])
    if force or reprint(fp):
        get_event_cache_all(ctx)
        get_character_relationships(ctx)
        pdf_template(ctx, "pdf/sheets/relationships.html", fp, True)
    return return_pdf(fp, f"{ctx['character']} - " + _("Relationships"))


def print_gallery(ctx, force=False):
    fp = ctx["run"].get_gallery_filepath()
    if force or reprint(fp):
        get_event_cache_all(ctx)
        ctx["first_aid"] = []
        for _num, el in ctx["chars"].items():
            if "first_aid" in el and el["first_aid"] == "y":
                ctx["first_aid"].append(el)
        fp = ctx["run"].get_gallery_filepath()
        xhtml_pdf(ctx, "pdf/sheets/gallery.html", fp)

    return return_pdf(fp, str(ctx["run"]) + " - " + _("Portraits"))


def print_profiles(ctx, force=False):
    fp = ctx["run"].get_profiles_filepath()
    if force or reprint(fp):
        get_event_cache_all(ctx)
        xhtml_pdf(ctx, "pdf/sheets/profiles.html", fp)
    return return_pdf(fp, str(ctx["run"]) + " - " + _("Profiles"))


def print_handout(ctx, force=True):
    fp = ctx["handout"].get_filepath(ctx["run"])
    if force or reprint(fp):
        ctx["handout"].data = ctx["handout"].show_complete()
        xhtml_pdf(ctx, "pdf/sheets/handout.html", fp)
    return return_pdf(fp, f"{ctx['handout'].data['name']}")


def print_volunteer_registry(ctx):
    fp = os.path.join(conf_settings.MEDIA_ROOT, f"volunteer_registry/{ctx['assoc'].slug}.pdf")
    xhtml_pdf(ctx, "pdf/volunteer_registry.html", fp)
    return fp


# ## HANDLE - DELETE FILES WHEN UPDATED


@receiver(pre_delete, sender=Handout)
def pre_delete_pdf_handout(sender, instance, **kwargs):
    for run in instance.event.runs.all():
        os.remove(instance.get_filepath(run))


@receiver(post_save, sender=Handout)
def post_save_pdf_handout(sender, instance, **kwargs):
    for run in instance.event.runs.all():
        os.remove(instance.get_filepath(run))


@receiver(pre_delete, sender=HandoutTemplate)
def pre_delete_pdf_handout_template(sender, instance, **kwargs):
    for run in instance.event.runs.all():
        for el in instance.handouts.all():
            os.remove(el.get_filepath(run))


@receiver(post_save, sender=HandoutTemplate)
def post_save_pdf_handout_template(sender, instance, **kwargs):
    for run in instance.event.runs.all():
        for el in instance.handouts.all():
            os.remove(el.get_filepath(run))


def safe_remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def remove_run_pdf(event):
    for run in event.runs.all():
        safe_remove(run.get_profiles_filepath())
        safe_remove(run.get_gallery_filepath())


def remove_char_pdf(instance, single=None, runs=None):
    if not runs:
        runs = instance.event.runs.all()
    for run in runs:
        if single and run != single:
            continue
        safe_remove(instance.get_sheet_filepath(run))
        safe_remove(instance.get_sheet_friendly_filepath(run))
        safe_remove(instance.get_relationships_filepath(run))


@receiver(pre_delete, sender=Character)
def pre_delete_pdf_character(sender, instance, **kwargs):
    remove_run_pdf(instance.event)
    remove_char_pdf(instance)


@receiver(post_save, sender=Character)
def post_save_pdf_character(sender, instance, **kwargs):
    remove_run_pdf(instance.event)
    remove_char_pdf(instance)


@receiver(pre_delete, sender=PlayerRelationship)
def pre_delete_pdf_player_relationship(sender, instance, **kwargs):
    for el in instance.reg.rcrs.all():
        remove_char_pdf(el.character, instance.reg.run)


@receiver(post_save, sender=PlayerRelationship)
def post_save_pdf_player_relationship(sender, instance, **kwargs):
    for el in instance.reg.rcrs.all():
        remove_char_pdf(el.character, instance.reg.run)


@receiver(pre_delete, sender=Relationship)
def pre_delete_pdf_relationship(sender, instance, **kwargs):
    remove_char_pdf(instance.source)


@receiver(post_save, sender=Relationship)
def post_save_pdf_relationship(sender, instance, **kwargs):
    remove_char_pdf(instance.source)


@receiver(pre_delete, sender=Faction)
def pre_delete_pdf_faction(sender, instance, **kwargs):
    for char in instance.event.characters.all():
        remove_char_pdf(char)


@receiver(post_save, sender=Faction)
def post_save_pdf_faction(sender, instance, **kwargs):
    runs = instance.event.runs.all()
    for char in instance.characters.all():
        remove_char_pdf(char, runs=runs)


def remove_pdf_assignment_trait(instance):
    for casting in Casting.objects.filter(member=instance.member, run=instance.run, typ=instance.typ):
        casting.active = False
        casting.save()

    char = get_trait_character(instance.run, instance.trait.number)
    if char:
        remove_char_pdf(char, instance.run)


@receiver(pre_delete, sender=AssignmentTrait)
def pre_delete_pdf_assignment_trait(sender, instance, **kwargs):
    remove_pdf_assignment_trait(instance)


@receiver(post_save, sender=AssignmentTrait)
def post_save_assignment_trait(sender, instance, created, **kwargs):
    if not instance.member or not created:
        return

    remove_pdf_assignment_trait(instance)


# ## TASKS


def print_handout_go(ctx, c):
    get_handout(ctx, c)
    print_handout(ctx)


def get_fake_request(assoc_slug):
    request = HttpRequest()
    request.assoc = get_cache_assoc(assoc_slug)
    request.user = AnonymousUser()
    return request


@background_auto(queue="pdf")
def print_handout_bkg(a, s, n, c):
    request = get_fake_request(a)
    ctx = get_event_run(request, s, n)
    print_handout_go(ctx, c)


def print_character_go(ctx, c):
    try:
        get_char_check(None, ctx, c, False, True)
        print_character(ctx, True)
        print_character_friendly(ctx, True)
        print_character_rel(ctx, True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf")
def print_character_bkg(a, s, n, c):
    request = get_fake_request(a)
    ctx = get_event_run(request, s, n)
    print_character_go(ctx, c)


@background_auto(queue="pdf")
def print_run_bkg(a, s, n):
    request = get_fake_request(a)
    ctx = get_event_run(request, s, n)

    print_gallery(ctx)
    print_profiles(ctx)

    for ch in ctx["run"].event.get_elements(Character).values_list("number", flat=True):
        print_character_go(ctx, ch)

    for h in ctx["run"].event.get_elements(Handout).values_list("number", flat=True):
        print_handout_go(ctx, h)


# ## OLD PRINTING


def odt_template(ctx, char, fp, template, aux_template):
    attempt = 0
    excepts = []
    max_attempts = 5
    while attempt < max_attempts:
        try:
            exec_odt_template(ctx, char, fp, template, aux_template)
            return
        except Exception as e:
            print("Error in pdf creation")
            print(e)
            print(char)
            print(template)
            attempt += 1
            excepts.append(e)
            time.sleep(2)
    print("ERROR IN odt_template")
    print(excepts)


def exec_odt_template(ctx, char, fp, template, aux_template):
    working_dir = os.path.dirname(fp)
    working_dir = os.path.join(working_dir, str(char["number"]))
    # print(working_dir)
    # deletes file if existing
    if os.path.exists(fp):
        os.remove(fp)
    working_dir += "-work"
    # deletes directory if existing
    if os.path.exists(working_dir):
        # print("delete")
        shutil.rmtree(working_dir)
    os.makedirs(working_dir)
    zip_dir = os.path.join(working_dir, "zipdd")
    # creates directory
    os.makedirs(zip_dir)
    # unzip event template there
    os.chdir(zip_dir)
    os.system(f"unzip -q {template.path}")
    update_content(ctx, working_dir, zip_dir, char, aux_template)
    # zip back again
    os.chdir(zip_dir)
    os.system("zip -q -r ../out.odt *")
    # convert to pdf
    os.chdir(working_dir)
    # os.system("unoconv -f pdf out.odt")
    os.system("/usr/bin/unoconv -f pdf out.odt")
    # move
    os.rename("out.pdf", fp)
    # ## TODO shutil.rmtree(working_dir)
    # if os.path.exists(working_dir):
    # shutil.rmtree(working_dir)


# translate html markup to odt
def get_odt_content(ctx, working_dir, aux_template):
    html = aux_template.render(ctx)
    # get odt teaser
    o_html = os.path.join(working_dir, "auxiliary.html")
    f = open(o_html, "w")
    f.write(html)
    f.close()
    # convert to odt
    os.chdir(working_dir)
    os.system("soffice --headless --convert-to odt auxiliary.html")
    # extract zip
    aux_dir = os.path.join(working_dir, "aux")
    if os.path.exists(aux_dir):
        shutil.rmtree(aux_dir)
    os.makedirs(aux_dir)
    os.chdir(aux_dir)
    os.system("unzip -q ../aux.odt")
    # get data from content
    doc = lxml.etree.parse("content.xml")
    txt = doc.xpath('//*[local-name()="text"]')[0]
    auto = doc.xpath('//*[local-name()="automatic-styles"]')[0]
    # get data from styles
    doc = lxml.etree.parse("styles.xml")
    styles = doc.xpath('//*[local-name()="styles"]')[0]
    return {
        "txt": txt.getchildren(),
        "auto": auto.getchildren(),
        "styles": styles.getchildren(),
    }


def clean_tag(tag):
    i = tag.find("}")
    if i >= 0:
        tag = tag[i + 1 :]
    return tag


def replace_data(path, char):
    with open(path) as file:
        filedata = file.read()

    for s in ["number", "name", "title"]:
        if s not in char:
            continue
        filedata = filedata.replace(f"#{s}#", str(char[s]))

    # Write the file out again
    with open(path, "w") as file:
        file.write(filedata)


def update_content(ctx, working_dir, zip_dir, char, aux_template):
    # ## NOW CONTENT
    content = os.path.join(zip_dir, "content.xml")
    replace_data(content, char)
    doc = lxml.etree.parse(content)
    elements = get_odt_content(ctx, working_dir, aux_template)

    styles = doc.xpath('//*[local-name()="automatic-styles"]')[0]
    for ch in styles.getchildren():
        styles.remove(ch)
    for ch in elements["auto"]:
        master_page = None
        for k in ch.attrib.keys():
            if clean_tag(k) == "master-page-name":
                master_page = k
        if master_page is not None:
            del ch.attrib[master_page]
        styles.append(ch)

    cnt = doc.xpath('//*[text()="@content@"]')
    if cnt:
        cnt = cnt[0]
        prnt = cnt.getparent()
        prnt.remove(cnt)
        for e in elements["txt"]:
            if clean_tag(e.tag) == "sequence-decls":
                continue
            prnt.append(e)

    doc.write(content, pretty_print=True)

    # ## NOW STYLE
    content = os.path.join(zip_dir, "styles.xml")
    replace_data(content, char)
    doc = lxml.etree.parse(content)
    styles = doc.xpath('//*[local-name()="styles"]')[0]
    # pprint(styles)
    for ch in elements["styles"]:
        # ~ Skip = false
        # ~ if ch.tag.endswith("default-style"):
        # ~ skip = True
        # ~ for key in ch.attrib:
        # ~ if key.endswith("name") and ch.attrib[key] in ["Footer", "Header", "Title", "Subtitle", "Text_20_body", "Heading_20_1", "Heading_20_2"]:
        # ~ skip = True
        # ~ if skip:
        # ~ continue
        styles.append(ch)

    doc.write(content, pretty_print=True)


def get_trait_character(run, number):
    try:
        tr = Trait.objects.get(event=run.event, number=number)
        mb = AssignmentTrait.objects.get(run=run, trait=tr).member
        rcrs = RegistrationCharacterRel.objects.filter(reg__run=run, reg__member=mb).select_related("character")
        if rcrs.count() == 0:
            return None
        return rcrs.first().character
    except ObjectDoesNotExist:
        return None
