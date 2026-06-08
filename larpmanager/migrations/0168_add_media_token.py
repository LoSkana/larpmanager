# Migration to add media_token fields and rename existing PDFs to token-based names

import logging
from pathlib import Path

from django.conf import settings as conf_settings
from django.db import migrations, models

import larpmanager.models.utils

log = logging.getLogger(__name__)


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
            return
        existing = set(Model.objects.exclude(media_token__isnull=True).values_list("media_token", flat=True))
        for inst in instances:
            while True:
                token = larpmanager.models.utils.my_uuid(32)
                if token not in existing:
                    inst.media_token = token
                    existing.add(token)
                    break
        Model.objects.bulk_update(instances, ["media_token"], batch_size=500)

    # ── Token assignment (always runs, even without media files) ─────────────

    writing_models = [
        "Character", "Plot", "Faction", "PrologueType", "Prologue",
        "Handout", "SpeedLarp", "QuestType", "Quest", "Trait",
    ]
    Run = apps.get_model("larpmanager", "Run")
    Member = apps.get_model("larpmanager", "Member")

    for model_name in writing_models:
        assign_tokens(apps.get_model("larpmanager", model_name))

    # Run tokens must be assigned before character/faction directory renames below.
    assign_tokens(Run)
    assign_tokens(Member)

    # ── File operations — skipped when MEDIA_ROOT/pdf is absent ──────────────
    # In CI containers or environments without a mounted media volume the renames
    # are a no-op.  Guard here makes the skip explicit and logged rather than
    # silently doing nothing while leaving files at their old paths.

    pdf_root = Path(conf_settings.MEDIA_ROOT) / "pdf"
    if not pdf_root.exists():
        log.warning(
            "MEDIA_ROOT/pdf not found (%s); skipping PDF file renames. "
            "Re-run this migration on a host with the media volume mounted, "
            "or move files manually: characters/{run.number}/ → {run.number}-{run.media_token}/characters/, "
            "factions/{run.number}/ → {run.number}-{run.media_token}/factions/, "
            "handouts/H{n}.pdf → handouts/{n}-{token}.pdf, "
            "members/{id}/ → members/{id}-{token}/.",
            pdf_root,
        )
        return

    # ── Rename Character PDFs then move directory into run token dir ──────────
    # Old layout: characters/{run.number}/#{char.number}.pdf
    # New layout: {run.number}-{run.media_token}/characters/{char.number}-{char.media_token}-full.pdf

    Character = apps.get_model("larpmanager", "Character")
    for char in Character.objects.select_related("event").iterator():
        if not char.event or not char.event.slug:
            continue
        event_dir = _event_media(char.event.slug)
        for run in Run.objects.filter(event_id=char.event_id).iterator():
            char_dir = event_dir / "characters" / str(run.number)
            for old_name, new_name in [
                (f"#{char.number}.pdf", f"{char.number}-{char.media_token}-full.pdf"),
                (f"#{char.number}-light.pdf", f"{char.number}-{char.media_token}-light.pdf"),
                (f"#{char.number}-rels.pdf", f"{char.number}-{char.media_token}-rels.pdf"),
            ]:
                _rename(char_dir / old_name, char_dir / new_name)

    for run in Run.objects.select_related("event").iterator():
        if not run.event or not run.event.slug:
            continue
        event_dir = _event_media(run.event.slug)
        old_char_dir = event_dir / "characters" / str(run.number)
        new_char_dir = event_dir / f"{run.number}-{run.media_token}" / "characters"
        if old_char_dir.exists() and not new_char_dir.exists():
            new_char_dir.parent.mkdir(parents=True, exist_ok=True)
            old_char_dir.rename(new_char_dir)

    # ── Rename Faction PDFs then move directory into run token dir ────────────
    # Old layout: factions/{run.number}/#{faction.number}.pdf
    # New layout: {run.number}-{run.media_token}/factions/{faction.number}-{faction.media_token}.pdf

    Faction = apps.get_model("larpmanager", "Faction")
    for faction in Faction.objects.select_related("event").iterator():
        if not faction.event or not faction.event.slug:
            continue
        event_dir = _event_media(faction.event.slug)
        for run in Run.objects.filter(event_id=faction.event_id).iterator():
            faction_dir = event_dir / "factions" / str(run.number)
            _rename(
                faction_dir / f"#{faction.number}.pdf",
                faction_dir / f"{faction.number}-{faction.media_token}.pdf",
            )

    for run in Run.objects.select_related("event").iterator():
        if not run.event or not run.event.slug:
            continue
        event_dir = _event_media(run.event.slug)
        old_faction_dir = event_dir / "factions" / str(run.number)
        new_faction_dir = event_dir / f"{run.number}-{run.media_token}" / "factions"
        if old_faction_dir.exists() and not new_faction_dir.exists():
            new_faction_dir.parent.mkdir(parents=True, exist_ok=True)
            old_faction_dir.rename(new_faction_dir)

    # ── Rename Handout PDFs ───────────────────────────────────────────────────
    # Old layout: handouts/H{handout.number}.pdf
    # New layout: handouts/{handout.number}-{handout.media_token}.pdf

    Handout = apps.get_model("larpmanager", "Handout")
    for handout in Handout.objects.select_related("event").iterator():
        if not handout.event or not handout.event.slug:
            continue
        handouts_dir = _event_media(handout.event.slug) / "handouts"
        _rename(handouts_dir / f"H{handout.number}.pdf", handouts_dir / f"{handout.number}-{handout.media_token}.pdf")

    # ── Run PDFs (gallery / profiles) ────────────────────────────────────────
    # run.get_media_filepath() now returns pdf/{event.slug}/{run.number}-{run.media_token}/
    # so move files from the old {run.number}/ directory into the new token-named directory.

    for run in Run.objects.select_related("event").iterator():
        if not run.event or not run.event.slug:
            continue
        event_dir = _event_media(run.event.slug)
        old_run_dir = event_dir / str(run.number)
        new_run_dir = event_dir / f"{run.number}-{run.media_token}"
        new_run_dir.mkdir(parents=True, exist_ok=True)
        _rename(old_run_dir / "gallery.pdf", new_run_dir / "gallery.pdf")
        _rename(old_run_dir / "profiles.pdf", new_run_dir / "profiles.pdf")

    # ── Member PDFs ───────────────────────────────────────────────────────────
    # get_member_filepath() now returns pdf/members/{member.id}-{media_token}/
    # so move files from the old {member.id}/ directory into the new token-named directory.

    for member in Member.objects.iterator():
        old_member_dir = Path(conf_settings.MEDIA_ROOT) / "pdf" / "members" / str(member.id)
        new_member_dir = Path(conf_settings.MEDIA_ROOT) / "pdf" / "members" / f"{member.id}-{member.media_token}"
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
