import os
from difflib import SequenceMatcher

import deepl
from bs4 import BeautifulSoup
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from whoosh.fields import ID, TEXT, Schema
from whoosh.index import create_in, open_dir
from whoosh.qparser import QueryParser

from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.event import Run
from larpmanager.models.larpmanager import LarpManagerTutorial
from larpmanager.utils.tasks import background_auto, notify_admins

INDEX_DIR = "data/whoosh_index"


def get_or_create_index(index_dir):
    schema = Schema(
        tutorial_id=ID(stored=True),
        slug=TEXT(stored=True),
        title=TEXT(stored=True),
        section_title=TEXT(stored=True),
        content=TEXT(stored=True),
    )
    if not os.path.exists(index_dir):
        os.mkdir(index_dir)
        return create_in(index_dir, schema, "MAIN")
    return open_dir(index_dir, "MAIN")


@background_auto(queue="whoosh")
def index_tutorial(tutorial_id):
    try:
        instance = LarpManagerTutorial.objects.get(pk=tutorial_id)
    except ObjectDoesNotExist:
        return

    ix = get_or_create_index(INDEX_DIR)
    writer = ix.writer()
    writer.delete_by_term("tutorial_id", str(tutorial_id))

    soup = BeautifulSoup(instance.descr, "html.parser")
    for section in soup.find_all(["h2", "h3"]):
        content = []
        for sib in section.find_next_siblings():
            if sib.name in ["h2", "h3"]:
                break
            content.append(sib.get_text())
        writer.add_document(
            tutorial_id=str(tutorial_id),
            slug=instance.slug,
            title=instance.name,
            section_title=section.get_text(),
            content="\n".join(content),
        )
    writer.commit()


@background_auto(queue="whoosh")
def delete_index(tutorial_id):
    ix = get_or_create_index(INDEX_DIR)
    writer = ix.writer()
    writer.delete_by_term("tutorial_id", str(tutorial_id))
    writer.commit()


def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_sorted_permissions(model, query):
    permissions = model.objects.filter(Q(name__icontains=query) | Q(descr__icontains=query)).values(
        "name", "slug", "descr"
    )
    return sorted(permissions, key=lambda p: similarity(p["name"], query), reverse=True)


def query_index(request):
    orig_string = request.POST.get("q", "")
    run_id = int(request.POST.get("r", "0"))

    # translate it
    translator = deepl.Translator(conf_settings.DEEPL_API_KEY)
    query_string = str(translator.translate_text(orig_string, target_lang="EN-US"))

    # notify admins
    notify_admins(f"query_index: {query_string}", f"{orig_string} - {request.user}")

    # get links
    if run_id:
        try:
            run = Run.objects.select_related("event").get(pk=run_id, event__assoc_id=request.assoc["id"])
        except ObjectDoesNotExist:
            return JsonResponse({})

        sorted_permissions = get_sorted_permissions(EventPermission, query_string)
        links = [
            {
                "name": perm["name"],
                "descr": perm["descr"],
                "href": reverse(perm["slug"], args=[run.event.slug, run.number]),
            }
            for perm in sorted_permissions
        ]
    else:
        sorted_permissions = get_sorted_permissions(AssocPermission, query_string)
        links = [
            {"name": perm["name"], "descr": perm["descr"], "href": reverse(perm["slug"])} for perm in sorted_permissions
        ]

    # get tutorials
    ix = get_or_create_index(INDEX_DIR)
    with ix.searcher() as searcher:
        query = QueryParser("content", ix.schema).parse(query_string)
        results = searcher.search(query, limit=10)
        tutorials = [
            {"slug": r["slug"], "title": r["title"], "section": r["section_title"], "snippet": r["content"][:300]}
            for r in results
        ]
    return JsonResponse({"tutorials": tutorials, "links": links}, safe=False)
