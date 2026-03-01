from __future__ import annotations

from django.core.files.storage import default_storage
from django.db import migrations

CSS_DELIMITER = "/*@#§*/"


def _has_custom_css(css_code: str, css_path: str) -> bool:
    """Return True if the CSS file exists and has user content before the delimiter."""
    if not css_code:
        return False
    try:
        if not default_storage.exists(css_path):
            return False
        content = default_storage.open(css_path).read().decode("utf-8")
        user_content = content.split(CSS_DELIMITER)[0] if CSS_DELIMITER in content else content
        return bool(user_content.strip())
    except (OSError, UnicodeDecodeError):
        return False


def _pick_theme(has_customisation: bool) -> str:  # noqa: FBT001
    return "halo" if has_customisation else "eclipse"


def set_themes(apps, schema_editor):  # noqa: ANN001
    Association = apps.get_model("larpmanager", "Association")
    AssociationConfig = apps.get_model("larpmanager", "AssociationConfig")
    Event = apps.get_model("larpmanager", "Event")
    EventConfig = apps.get_model("larpmanager", "EventConfig")

    for assoc in Association.objects.filter(deleted=None).exclude(id=0):
        css_path = f"css/{assoc.slug}_{assoc.css_code}.css"
        has_customisation = bool(
            assoc.background
            or assoc.pri_rgb
            or assoc.sec_rgb
            or assoc.ter_rgb
            or _has_custom_css(assoc.css_code, css_path)
        )
        theme = _pick_theme(has_customisation)
        AssociationConfig.objects.get_or_create(
            association=assoc,
            name="theme",
            deleted=None,
            defaults={"value": theme},
        )

    for event in Event.objects.filter(deleted=None):
        css_path = f"css/{event.association.slug}_{event.slug}_{event.css_code}.css"
        has_customisation = bool(
            event.background
            or event.pri_rgb
            or event.sec_rgb
            or event.ter_rgb
            or _has_custom_css(event.css_code, css_path)
        )
        theme = _pick_theme(has_customisation)
        EventConfig.objects.get_or_create(
            event=event,
            name="theme",
            deleted=None,
            defaults={"value": theme},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0144_milestone"),
    ]

    operations = [
        migrations.RunPython(set_themes, migrations.RunPython.noop),
    ]
