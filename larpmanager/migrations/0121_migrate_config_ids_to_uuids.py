# Migration to convert question/option IDs to UUIDs in RunConfig and MemberConfig

import ast
import re
from typing import Any

from django.db import migrations


def migrate_config_ids_to_uuids(apps: Any, schema_editor: Any) -> None:
    """Migrate question/option IDs to UUIDs in RunConfig and MemberConfig values.

    Converts config list values that contain question/option references from ID-based
    format (e.g., 'q_123', '.lq_456') to UUID-based format (e.g., 'q_abc123def456').

    Affected configs:
    - RunConfig: show_character, show_faction, show_quest, show_trait, show_addit
    - MemberConfig: open_registration_*, open_character_*, open_faction_*, open_quest_*, open_trait_*
    """
    RunConfig = apps.get_model("larpmanager", "RunConfig")
    MemberConfig = apps.get_model("larpmanager", "MemberConfig")
    WritingQuestion = apps.get_model("larpmanager", "WritingQuestion")
    WritingOption = apps.get_model("larpmanager", "WritingOption")
    RegistrationQuestion = apps.get_model("larpmanager", "RegistrationQuestion")
    RegistrationOption = apps.get_model("larpmanager", "RegistrationOption")

    # Build ID to UUID mappings for all question and option types
    question_id_to_uuid = {}
    option_id_to_uuid = {}

    # WritingQuestion and WritingOption mappings
    for question_id, question_uuid in WritingQuestion.objects.values_list('id', 'uuid'):
        question_id_to_uuid[str(question_id)] = question_uuid

    for option_id, option_uuid in WritingOption.objects.values_list('id', 'uuid'):
        option_id_to_uuid[str(option_id)] = option_uuid

    # RegistrationQuestion and RegistrationOption mappings
    for question_id, question_uuid in RegistrationQuestion.objects.values_list('id', 'uuid'):
        question_id_to_uuid[str(question_id)] = question_uuid

    for option_id, option_uuid in RegistrationOption.objects.values_list('id', 'uuid'):
        option_id_to_uuid[str(option_id)] = option_uuid

    def convert_element(element: str) -> str:
        """Convert a single element from ID to UUID format.

        Args:
            element: Config element like 'q_123', '.lq_456', or 'email'

        Returns:
            Converted element with UUID, or original if not a question/option reference
        """
        # Pattern: 'q_123' or '.lq_123' - capture prefix and ID
        match = re.match(r'^(\.?lq_|q_)(\d+)$', element)
        if not match:
            # Not a question/option reference, return as-is
            return element

        prefix, item_id = match.groups()

        # Try to find UUID in question mapping first, then option mapping
        uuid = question_id_to_uuid.get(item_id) or option_id_to_uuid.get(item_id)

        if uuid:
            return f"{prefix}{uuid}"

        # ID not found in mappings - might be deleted, return original
        return element

    def migrate_config_list(config_value: str) -> str:
        """Migrate a config list value from IDs to UUIDs.

        Args:
            config_value: String representation of list, e.g., "['q_123', '.lq_456']"

        Returns:
            Updated string with UUIDs
        """
        try:
            # Parse the list
            element_list = ast.literal_eval(config_value)

            # Skip if not a list
            if not isinstance(element_list, list):
                return config_value

            # Skip if empty
            if not element_list:
                return config_value

            # Check if already migrated - UUIDs are 12 characters
            first_element = str(element_list[0])
            if re.match(r'^(\.?lq_|q_)[a-zA-Z0-9]{12}$', first_element):
                # Already uses UUIDs
                return config_value

            # Convert each element
            migrated_list = [convert_element(str(elem)) for elem in element_list]

            # Return as string representation
            return str(migrated_list)

        except (ValueError, SyntaxError, AttributeError):
            # Invalid format, return unchanged
            return config_value

    # Migrate RunConfig entries
    run_config_patterns = ['show_character', 'show_faction', 'show_quest', 'show_trait', 'show_addit']
    run_configs_to_update = []

    for config in RunConfig.objects.filter(name__in=run_config_patterns):
        original_value = config.value
        migrated_value = migrate_config_list(original_value)

        if migrated_value != original_value:
            config.value = migrated_value
            run_configs_to_update.append(config)

    if run_configs_to_update:
        RunConfig.objects.bulk_update(run_configs_to_update, ['value'], batch_size=100)

    # Migrate MemberConfig entries
    # Pattern: open_registration_{event_id}, open_character_{event_id}, etc.
    member_configs_to_update = []

    for config in MemberConfig.objects.filter(name__regex=r'^open_(registration|character|faction|quest|trait)_\d+$'):
        original_value = config.value
        migrated_value = migrate_config_list(original_value)

        if migrated_value != original_value:
            config.value = migrated_value
            member_configs_to_update.append(config)

    if member_configs_to_update:
        MemberConfig.objects.bulk_update(member_configs_to_update, ['value'], batch_size=100)


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0120_alter_larpmanagerticket_priority_and_more'),
    ]

    operations = [
        migrations.RunPython(
            migrate_config_ids_to_uuids,
            reverse_code=migrations.RunPython.noop
        ),
    ]
