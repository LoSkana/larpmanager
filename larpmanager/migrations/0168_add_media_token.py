# Migration to add media_token fields and rename existing PDFs to token-based names

from pathlib import Path

from django.conf import settings as conf_settings
from django.db import migrations, models

import larpmanager.models.utils


def _event_media(event_slug):
    return Path(conf_settings.MEDIA_ROOT) / "pdf" / event_slug


def _rename(old_path, new_path):
    if old_path.exists() and not new_path.exists():
        old_path.rename(new_path)


def populate_tokens_and_rename_pdfs(apps, schema_editor):
    """Populate media_token for all models and rename existing PDF files."""

    # ── helpers ──────────────────────────────────────────────────────────────

    def assign_tokens(Model):
        instances = list(Model.objects.filter(media_token__isnull=True))
        if not instances:
            return instances
        existing = set(Model.objects.exclude(media_token__isnull=True).values_list("media_token", flat=True))
        for inst in instances:
            while True:
                token = larpmanager.models.utils.my_uuid(32)
                if token not in existing:
                    inst.media_token = token
                    existing.add(token)
                    break
        Model.objects.bulk_update(instances, ["media_token"], batch_size=500)
        return instances

    # ── Writing subclasses (Character, Faction, Handout, others) ─────────────

    writing_models = [
        "Character", "Plot", "Faction", "PrologueType", "Prologue",
        "Handout", "SpeedLarp", "QuestType", "Quest", "Trait",
    ]
    Run = apps.get_model("larpmanager", "Run")

    for model_name in writing_models:
        Model = apps.get_model("larpmanager", model_name)
        assign_tokens(Model)

    # ── Rename Character PDFs ─────────────────────────────────────────────────

    Character = apps.get_model("larpmanager", "Character")
    for char in Character.objects.select_related("event").iterator():
        event_dir = _event_media(char.event.slug)
        for run in Run.objects.filter(event_id=char.event_id).iterator():
            char_dir = event_dir / "characters" / str(run.number)
            for old_name, suffix in [
                (f"#{char.number}.pdf", ".pdf"),
                (f"#{char.number}-light.pdf", "-light.pdf"),
                (f"#{char.number}-rels.pdf", "-rels.pdf"),
            ]:
                _rename(char_dir / old_name, char_dir / f"{char.media_token}{suffix}")

    # ── Rename Faction PDFs ───────────────────────────────────────────────────

    Faction = apps.get_model("larpmanager", "Faction")
    for faction in Faction.objects.select_related("event").iterator():
        event_dir = _event_media(faction.event.slug)
        for run in Run.objects.filter(event_id=faction.event_id).iterator():
            faction_dir = event_dir / "factions" / str(run.number)
            _rename(
                faction_dir / f"#{faction.number}.pdf",
                faction_dir / f"{faction.media_token}.pdf",
            )

    # ── Rename Handout PDFs ───────────────────────────────────────────────────

    Handout = apps.get_model("larpmanager", "Handout")
    for handout in Handout.objects.select_related("event").iterator():
        handouts_dir = _event_media(handout.event.slug) / "handouts"
        for run in Run.objects.filter(event_id=handout.event_id).iterator():
            run_handouts_dir = _event_media(handout.event.slug) / str(run.number) / "handouts"
            for d in [handouts_dir, run_handouts_dir]:
                _rename(d / f"H{handout.number}.pdf", d / f"{handout.media_token}.pdf")

    # ── Run PDFs (gallery / profiles) ────────────────────────────────────────
    # run.get_media_filepath() now returns pdf/{event.slug}/{run.media_token}/
    # so move files from the old {run.number}/ directory into the new token-named directory.

    assign_tokens(Run)
    for run in Run.objects.select_related("event").iterator():
        old_run_dir = _event_media(run.event.slug) / str(run.number)
        new_run_dir = _event_media(run.event.slug) / str(run.media_token)
        new_run_dir.mkdir(parents=True, exist_ok=True)
        _rename(old_run_dir / "gallery.pdf", new_run_dir / "gallery.pdf")
        _rename(old_run_dir / "profiles.pdf", new_run_dir / "profiles.pdf")

    # ── Member PDFs ───────────────────────────────────────────────────────────
    # get_member_filepath() now returns pdf/members/{media_token}/
    # so move files from the old {member.id}/ directory into the new token-named directory.

    Member = apps.get_model("larpmanager", "Member")
    assign_tokens(Member)
    for member in Member.objects.iterator():
        old_member_dir = Path(conf_settings.MEDIA_ROOT) / "pdf" / "members" / str(member.id)
        new_member_dir = Path(conf_settings.MEDIA_ROOT) / "pdf" / "members" / str(member.media_token)
        new_member_dir.mkdir(parents=True, exist_ok=True)
        _rename(old_member_dir / "request.pdf", new_member_dir / "request.pdf")


model_names = [
    "character", "plot", "faction", "prologuetype", "prologue",
    "handout", "speedlarp", "questtype", "quest", "trait",
    "run", "member",
]


class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0167_alter_abilityexp_system_alter_deliveryexp_system"),
    ]

    operations = []

    # Step 1: Add media_token as nullable (no unique constraint yet)
    for model_name in model_names:
        operations.append(
            migrations.AddField(
                model_name=model_name,
                name="media_token",
                field=models.CharField(
                    default=None,
                    editable=False,
                    max_length=32,
                    null=True,
                    db_index=False,
                ),
            )
        )

    # Step 2: Populate tokens and rename existing PDFs
    operations.append(
        migrations.RunPython(populate_tokens_and_rename_pdfs, migrations.RunPython.noop)
    )

    # Step 3: Add unique constraint and make non-nullable
    for model_name in model_names:
        operations.append(
            migrations.AlterField(
                model_name=model_name,
                name="media_token",
                field=models.CharField(
                    editable=False,
                    max_length=32,
                    unique=True,
                    db_index=True,
                ),
            )
        )
