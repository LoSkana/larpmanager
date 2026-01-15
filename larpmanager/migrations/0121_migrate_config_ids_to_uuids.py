# Migration to convert question/option IDs to UUIDs in RunConfig and MemberConfig

import ast
import re
from typing import Any
from django.db import migrations


def migrate_config_ids_to_uuids(apps: Any, schema_editor: Any) -> None:
    RunConfig = apps.get_model("larpmanager", "RunConfig")
    MemberConfig = apps.get_model("larpmanager", "MemberConfig")
    WritingQuestion = apps.get_model("larpmanager", "WritingQuestion")
    WritingOption = apps.get_model("larpmanager", "WritingOption")
    RegistrationQuestion = apps.get_model("larpmanager", "RegistrationQuestion")
    RegistrationOption = apps.get_model("larpmanager", "RegistrationOption")

    question_id_to_uuid = {}
    option_id_to_uuid = {}

    for _id, _uuid in WritingQuestion.objects.values_list("id", "uuid"):
        question_id_to_uuid[str(_id)] = str(_uuid)

    for _id, _uuid in RegistrationQuestion.objects.values_list("id", "uuid"):
        question_id_to_uuid[str(_id)] = str(_uuid)

    for _id, _uuid in WritingOption.objects.values_list("id", "uuid"):
        option_id_to_uuid[str(_id)] = str(_uuid)

    for _id, _uuid in RegistrationOption.objects.values_list("id", "uuid"):
        option_id_to_uuid[str(_id)] = str(_uuid)

    UUID_RE = re.compile(r"^[a-z0-9]{12}$", re.IGNORECASE)

    def convert_element(element: str) -> str:
        # già UUID con prefisso
        m = re.match(r"^(\.?lq_|q_)([a-z0-9]{12})$", element, re.IGNORECASE)
        if m:
            return element

        # prefisso + ID numerico
        m = re.match(r"^(\.?lq_|q_)(\d+)$", element)
        if m:
            prefix, item_id = m.groups()
            uuid = question_id_to_uuid.get(item_id) or option_id_to_uuid.get(item_id)
            return f"{prefix}{uuid}" if uuid else element

        # ID numerico puro
        if element.isdigit():
            uuid = question_id_to_uuid.get(element) or option_id_to_uuid.get(element)
            return uuid if uuid else element

        return element

    def migrate_config_list(value: str) -> str:
        try:
            data = ast.literal_eval(value)
            if not isinstance(data, list):
                return value

            migrated = [convert_element(str(el)) for el in data]
            return str(migrated) if migrated != data else value
        except Exception:
            return value

    run_names = [
        "show_character",
        "show_faction",
        "show_quest",
        "show_trait",
        "show_addit",
    ]

    run_to_update = []
    for cfg in RunConfig.objects.filter(name__in=run_names):
        new_val = migrate_config_list(cfg.value)
        if new_val != cfg.value:
            cfg.value = new_val
            run_to_update.append(cfg)

    if run_to_update:
        RunConfig.objects.bulk_update(run_to_update, ["value"], batch_size=100)

    member_to_update = []
    for cfg in MemberConfig.objects.filter(
        name__regex=r"^open_(registration|character|faction|quest|trait|plot)_\d+$"
    ):
        new_val = migrate_config_list(cfg.value)
        if new_val != cfg.value:
            cfg.value = new_val
            member_to_update.append(cfg)

    if member_to_update:
        MemberConfig.objects.bulk_update(member_to_update, ["value"], batch_size=100)


class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0120_alter_larpmanagerticket_priority_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_config_ids_to_uuids,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
