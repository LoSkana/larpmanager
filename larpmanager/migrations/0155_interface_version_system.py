from typing import Any

from django.db import migrations


def migrate_interface_versions(apps: Any, schema_editor: Any) -> None:
    """Convert legacy interface flag configs to the new numeric version system.

    For each association, derive its version from the old flag combination and
    create an AssociationConfig(name="version") entry. Then remove all legacy
    flag configs.

    For each member, convert the three legacy toggle configs into a single
    interface_version value, then remove the old toggle configs.
    """
    Association = apps.get_model("larpmanager", "Association")
    AssociationConfig = apps.get_model("larpmanager", "AssociationConfig")
    MemberConfig = apps.get_model("larpmanager", "MemberConfig")

    # --- Association: set version config from legacy flags ---
    for assoc in Association.objects.all():
        configs = {
            c.name: c.value
            for c in AssociationConfig.objects.filter(
                association=assoc,
                name__in=["old_dashboard", "old_form_appearance", "old_menu_appearance"],
            )
        }

        old_dash = configs.get("old_dashboard", "False") == "True"
        old_form = configs.get("old_form_appearance", "False") == "True"
        old_menu = configs.get("old_menu_appearance", "False") == "True"

        if old_dash and old_form and old_menu:
            version = 16
        elif not old_dash and old_form and old_menu:
            version = 17
        elif not old_dash and not old_form and old_menu:
            version = 18
        else:
            version = 19

        if not AssociationConfig.objects.filter(association=assoc, name="version").exists():
            AssociationConfig.objects.create(association=assoc, name="version", value=str(version))

    # --- Remove legacy association flag configs ---
    AssociationConfig.objects.filter(
        name__in=["old_dashboard", "old_form_appearance", "old_menu_appearance"],
    ).delete()

    # --- Member: convert 3 toggle configs to interface_version ---
    member_ids = (
        MemberConfig.objects.filter(
            name__in=["interface_new_dashboard", "interface_new_ui", "interface_new_menu"],
            value="True",
        )
        .values_list("member_id", flat=True)
        .distinct()
    )

    for member_id in member_ids:
        configs = {
            c.name: c.value
            for c in MemberConfig.objects.filter(
                member_id=member_id,
                name__in=["interface_new_dashboard", "interface_new_ui", "interface_new_menu"],
            )
        }

        new_menu = configs.get("interface_new_menu") == "True"
        new_ui = configs.get("interface_new_ui") == "True"
        new_dash = configs.get("interface_new_dashboard") == "True"

        if new_menu:
            version = 19
        elif new_ui:
            version = 18
        elif new_dash:
            version = 17
        else:
            continue

        if not MemberConfig.objects.filter(member_id=member_id, name="interface_version").exists():
            MemberConfig.objects.create(member_id=member_id, name="interface_version", value=str(version))

    # --- Remove legacy member toggle configs ---
    MemberConfig.objects.filter(
        name__in=["interface_new_dashboard", "interface_new_ui", "interface_new_menu"],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0154_player_relationships_feature"),
    ]

    operations = [
        migrations.RunPython(migrate_interface_versions, migrations.RunPython.noop),
    ]
