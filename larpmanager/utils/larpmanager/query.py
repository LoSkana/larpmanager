from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import deepl
from bs4 import BeautifulSoup
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from whoosh.fields import ID, TEXT, Schema
from whoosh.index import create_in, open_dir
from whoosh.qparser import QueryParser

from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.event import Run
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial
from larpmanager.utils.larpmanager.tasks import background_auto, notify_admins

TUTORIAL_INDEX = "data/whoosh/tutorial_index"

GUIDE_INDEX = "data/whoosh/GUIDE_INDEX"


def _save_index(index_dir: str, schema: Any) -> object:
    """Create or open a Whoosh index directory."""
    # Create directory if it doesn't exist and return new index
    if not Path(index_dir).exists():
        Path(index_dir).mkdir(parents=True, exist_ok=True)
        return create_in(index_dir, schema, "MAIN")

    # Open existing index directory
    return open_dir(index_dir, "MAIN")


def get_or_create_index_tutorial(tutorial_index_directory: str) -> object:
    """Get or create a tutorial search index with predefined schema."""
    # Define schema for tutorial search indexing
    tutorial_schema = Schema(
        tutorial_id=ID(stored=True),
        slug=TEXT(stored=True),
        title=TEXT(stored=True),
        section_title=TEXT(stored=True),
        content=TEXT(stored=True),
    )
    # Create and return the index using the defined schema
    return _save_index(tutorial_index_directory, tutorial_schema)


@background_auto(queue="whoosh")
def add_tutorial_to_search_index(tutorial_id: int) -> None:
    """Index tutorial content for search functionality.

    Parses tutorial HTML content to extract sections and indexes them
    for full-text search. Each H2/H3 section is indexed separately
    with its associated content.

    Args:
        tutorial_id: The primary key ID of the tutorial to index.

    Returns:
        None: Function performs indexing operations but returns nothing.

    Raises:
        No exceptions are raised - ObjectDoesNotExist is handled internally.

    """
    # Attempt to retrieve the tutorial instance
    try:
        instance = LarpManagerTutorial.objects.get(pk=tutorial_id)
    except ObjectDoesNotExist:
        return

    # Initialize search index and writer
    ix = get_or_create_index_tutorial(TUTORIAL_INDEX)
    writer = ix.writer()

    # Remove any existing index entries for this tutorial
    writer.delete_by_term("tutorial_id", str(tutorial_id))

    # Parse HTML content to extract sections
    soup = BeautifulSoup(instance.descr, "html.parser")

    # Process each section (H2/H3 headings)
    for section in soup.find_all(["h2", "h3"]):
        content = []

        # Collect content following this section until next heading
        for sib in section.find_next_siblings():
            if sib.name in ["h2", "h3"]:
                break
            content.append(sib.get_text())

        # Add section to search index
        writer.add_document(
            tutorial_id=str(tutorial_id),
            slug=instance.slug,
            title=instance.name,
            section_title=section.get_text(),
            content="\n".join(content),
        )

    # Commit changes to the index
    writer.commit()


@background_auto(queue="whoosh")
def remove_tutorial_from_search_index(tutorial_id: int) -> None:
    """Remove a tutorial from the search index by ID."""
    # Get or create the tutorial index
    ix = get_or_create_index_tutorial(TUTORIAL_INDEX)

    # Create writer and delete tutorial by ID
    writer = ix.writer()
    writer.delete_by_term("tutorial_id", str(tutorial_id))
    writer.commit()


def get_or_create_index_guide(index_directory_path: str) -> object:
    """Get or create a search index for guide documents."""
    # Define schema for guide documents with searchable fields
    guide_schema = Schema(
        guide_id=ID(stored=True),
        slug=TEXT(stored=True),
        title=TEXT(stored=True),
        content=TEXT(stored=True),
    )
    # Create or open the index using the defined schema
    return _save_index(index_directory_path, guide_schema)


@background_auto(queue="whoosh")
def add_guide_to_search_index(guide_id: Any) -> None:
    """Index a guide document for search functionality.

    Args:
        guide_id: ID of the LarpManagerGuide to index

    """
    try:
        instance = LarpManagerGuide.objects.get(pk=guide_id)
    except ObjectDoesNotExist:
        return

    if not instance.published:
        return

    ix = get_or_create_index_guide(GUIDE_INDEX)
    writer = ix.writer()
    writer.delete_by_term("guide_id", str(guide_id))

    soup = BeautifulSoup(instance.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    writer.add_document(
        guide_id=str(guide_id),
        slug=instance.slug,
        title=instance.title,
        content=text,
    )
    writer.commit()


@background_auto(queue="whoosh")
def remove_guide_from_search_index(guide_id: int) -> None:
    """Remove a guide from the search index by ID."""
    # Get or create the guide search index
    ix = get_or_create_index_guide(GUIDE_INDEX)

    # Create writer and delete guide by ID
    writer = ix.writer()
    writer.delete_by_term("guide_id", str(guide_id))
    writer.commit()


def similarity(first_string: str, second_string: str) -> float:
    """Calculate similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, first_string.lower(), second_string.lower()).ratio()


def get_sorted_permissions(model: type, query: str) -> list[dict[str, str]]:
    """Get permissions filtered by query and sorted by name similarity."""
    # Filter permissions by name or description containing the query
    permissions = model.objects.filter(Q(name__icontains=query) | Q(descr__icontains=query)).values(
        "name",
        "slug",
        "descr",
    )

    # Sort by similarity to query string, most similar first
    return sorted(permissions, key=lambda permission: similarity(permission["name"], query), reverse=True)


def query_index(request: HttpRequest) -> JsonResponse:
    """Handle search queries with translation support.

    Processes search requests and translates content using DeepL API,
    then searches through both permission-based navigation links, guides and
    tutorial content to provide relevant results.

    Args:
        request: Django HTTP request object containing POST data with:
            - q: Search query string
            - r: Optional run UUID for event-specific search

    Returns:
        JsonResponse containing search results with guides, tutorials, and links.
        Returns empty JsonResponse if run lookup fails.

    Raises:
        ObjectDoesNotExist: If specified run doesn't exist (handled internally)

    """
    # Extract and validate input parameters
    original_search_query: str = request.POST.get("q", "")
    run_uuid: str = request.POST.get("r", "")

    # Translate query string to English for consistent search
    translator = deepl.Translator(conf_settings.DEEPL_API_KEY)
    translated_query: str = str(translator.translate_text(original_search_query, target_lang="EN-US"))

    # Log search activity for admin monitoring
    notify_admins(f"query_index: {translated_query}", f"{original_search_query} - {request.user}")

    # Build permission-based navigation links
    permission_links: list[dict[str, str]] = []
    if run_uuid:
        # Event-specific permissions and links
        try:
            run = Run.objects.select_related("event").get(
                uuid=run_uuid, event__association_id=request.association["id"]
            )
        except ObjectDoesNotExist:
            return JsonResponse({})

        sorted_permissions: list[dict[str, Any]] = get_sorted_permissions(EventPermission, translated_query)
        permission_links = [
            {
                "name": permission["name"],
                "descr": permission["descr"],
                "href": reverse(permission["slug"], args=[run.get_slug()]),
            }
            for permission in sorted_permissions
        ]
    else:
        # Organization-wide permissions and links
        sorted_permissions = get_sorted_permissions(AssociationPermission, translated_query)
        permission_links = [
            {"name": permission["name"], "descr": permission["descr"], "href": reverse(permission["slug"])}
            for permission in sorted_permissions
        ]

    # Search through guide content using Whoosh index
    guide_index = get_or_create_index_tutorial(GUIDE_INDEX)
    with guide_index.searcher() as searcher:
        query = QueryParser("content", guide_index.schema).parse(translated_query)
        search_results = searcher.search(query, limit=5)
        matching_guides: list[dict[str, str]] = [
            {"slug": result["slug"], "title": result["title"], "snippet": result["content"][:300]}
            for result in search_results
        ]

    # Search through tutorial content using Whoosh index
    tutorial_index = get_or_create_index_tutorial(TUTORIAL_INDEX)
    with tutorial_index.searcher() as searcher:
        query = QueryParser("content", tutorial_index.schema).parse(translated_query)
        search_results = searcher.search(query, limit=10)
        matching_tutorials: list[dict[str, str]] = [
            {
                "slug": result["slug"],
                "title": result["title"],
                "section": result["section_title"],
                "snippet": result["content"][:300],
            }
            for result in search_results
        ]

    # Return consolidated search results
    return JsonResponse(
        {"guides": matching_guides, "tutorials": matching_tutorials, "links": permission_links},
        safe=False,
    )
