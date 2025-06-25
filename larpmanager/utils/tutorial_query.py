import os

from bs4 import BeautifulSoup
from django.http import JsonResponse
from whoosh.fields import TEXT, Schema
from whoosh.index import create_in, open_dir
from whoosh.qparser import QueryParser

from larpmanager.mail.base import notify_admins
from larpmanager.models.larpmanager import LarpManagerTutorial
from larpmanager.utils.tasks import background_auto

INDEX_DIR = "whoosh_index"


def get_or_create_index(index_dir):
    schema = Schema(
        slug=TEXT(stored=True), title=TEXT(stored=True), section_title=TEXT(stored=True), content=TEXT(stored=True)
    )
    if not os.path.exists(index_dir):
        os.mkdir(index_dir)
        return create_in(index_dir, schema)
    return open_dir(index_dir)


@background_auto(queue="whoosh")
def index_tutorial(tutorial_id):
    ix = get_or_create_index(INDEX_DIR)
    writer = ix.writer()
    writer.delete_by_term("tutorial_id", str(tutorial_id))

    instance = LarpManagerTutorial.objects.get(pk=tutorial_id)

    soup = BeautifulSoup(instance.descr, "html.parser")
    for section in soup.find_all(["h2", "h3"]):
        content = []
        for sib in section.find_next_siblings():
            if sib.name in ["h2", "h3"]:
                break
            content.append(sib.get_text())
        writer.add_document(
            slug=instance.slug, title=instance.name, section_title=section.get_text(), content="\n".join(content)
        )
    writer.commit()


@background_auto(queue="whoosh")
def delete_index(tutorial_id):
    ix = get_or_create_index(INDEX_DIR)
    writer = ix.writer()
    writer.delete_by_term("tutorial_id", str(tutorial_id))
    writer.commit()


def query_index(request):
    query_string = request.POST.get("q", "")
    notify_admins(f"query_index: {query_string}", "")
    ix = get_or_create_index(INDEX_DIR)
    with ix.searcher() as searcher:
        query = QueryParser("content", ix.schema).parse(query_string)
        results = searcher.search(query, limit=10)
        data = [
            {"slug": r["slug"], "title": r["title"], "section": r["section_title"], "snippet": r["content"][:300]}
            for r in results
        ]
    return JsonResponse(data, safe=False)
