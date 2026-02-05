# Generated manually

from typing import Any

from django.db import migrations, models
from django.utils import timezone


def copy_register_link_to_runs(apps: Any, schema_editor: Any) -> None:
    """Copy register_link from Event to all its Runs."""
    Run = apps.get_model("larpmanager", "Run")

    for run in Run.objects.select_related("event").all():
        if run.event and run.event.register_link:
            run.register_link = run.event.register_link
            run.save(update_fields=["register_link"])


def set_registration_status(apps: Any, schema_editor: Any) -> None:
    """Set registration_status based on existing feature and field values."""
    Run = apps.get_model("larpmanager", "Run")
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")

    # Get feature IDs for checking which events have them
    register_link_feature = Feature.objects.filter(slug="register_link").first()
    registration_open_feature = Feature.objects.filter(slug="registration_open").first()

    current_datetime = timezone.now()

    for run in Run.objects.select_related("event").all():
        # Check if event has register_link feature enabled
        has_register_link_feature = (
            register_link_feature
            and run.event.features.filter(id=register_link_feature.id).exists()
        )

        # Check if event has registration_open feature enabled
        has_registration_open_feature = (
            registration_open_feature
            and run.event.features.filter(id=registration_open_feature.id).exists()
        )

        # Check if pre_register_active config is True
        pre_register_active = EventConfig.objects.filter(
            event_id=run.event_id,
            name="pre_register_active",
            value="true",
        ).exists()

        # Determine the status based on priority
        # Use run.register_link since it was copied from event
        if has_register_link_feature and run.register_link:
            # External registration
            run.registration_status = "e"  # EXTERNAL
        elif has_registration_open_feature and run.registration_open:
            # Open in future
            run.registration_status = "f"  # FUTURE
        elif pre_register_active and not run.registration_open:
            # Pre-registration
            run.registration_status = "p"  # PRE
        elif run.end and run.end < current_datetime.date():
            # Past event - closed
            run.registration_status = "c"  # CLOSED
        else:
            # Default to closed for safety - organizers can open manually
            run.registration_status = "o"  # OPEN

        run.save(update_fields=["registration_status"])


def remove_features(apps: Any, schema_editor: Any) -> None:
    """Remove the registration_open and register_link features."""
    Feature = apps.get_model("larpmanager", "Feature")
    Feature.objects.filter(slug__in=["registration_open", "register_link"]).delete()


def remove_pre_register_active_configs(apps: Any, schema_editor: Any) -> None:
    """Remove the pre_register_active config values."""
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    EventConfig.objects.filter(name="pre_register_active").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0134_alter_event_max_filler_alter_event_max_pg_and_more"),
    ]

    operations = [
        # Add register_link to Run
        migrations.AddField(
            model_name="run",
            name="register_link",
            field=models.URLField(
                blank=True,
                max_length=150,
                verbose_name="External registration link",
                help_text="Link to an external registration system (non-registered users will be redirected here, while registered users get normal access)",
            ),
        ),
        # Add registration_status to Run
        migrations.AddField(
            model_name="run",
            name="registration_status",
            field=models.CharField(
                choices=[
                    ("c", "Closed"),
                    ("o", "Open"),
                    ("p", "Pre-registration"),
                    ("e", "External site"),
                    ("f", "Open on date"),
                ],
                default="c",
                help_text="Registration status for this event",
                max_length=1,
                verbose_name="Registration status",
            ),
        ),
        # Copy register_link from Event to Runs
        migrations.RunPython(copy_register_link_to_runs),
        # Set registration status based on existing data
        migrations.RunPython(set_registration_status),
        # Remove register_link from Event
        migrations.RemoveField(
            model_name="event",
            name="register_link",
        ),
        # Remove the features
        migrations.RunPython(remove_features),
        # Remove pre_register_active configs
        migrations.RunPython(remove_pre_register_active_configs),
        migrations.AlterField(
            model_name='run',
            name='registration_open',
            field=models.DateTimeField(blank=True, help_text='Date and time when registrations open for participants',
                                       null=True, verbose_name='Registration opening'),
        ),
        migrations.AlterField(
            model_name='run',
            name='registration_status',
            field=models.CharField(
                choices=[('p', 'Pre-registration'), ('c', 'Closed'), ('o', 'Open'), ('e', 'External site'),
                         ('f', 'Open on date')], default='c', help_text='Registrations status for this event',
                max_length=1, verbose_name='Registrations status'),
        ),
    ]
