# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
from __future__ import annotations

from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.upload.csv_file import _get_file, _read_uploaded_csv
from larpmanager.utils.io.upload.dispatch import go_upload
from larpmanager.utils.io.upload.experience import (
    _ability_load,
    _ability_type_load,
    _apply_ability_field,
    _apply_criterion_field,
    _apply_delivery_field,
    _apply_rule_field,
    _assign_rule_field,
    _criterion_load,
    _delivery_load,
    _find_delivery,
    _free_delivery_number,
    _modifier_load,
    _row_delivery_number,
    _rule_load,
    _skip_ability_field,
    abilities_load,
    ability_types_load,
    criterions_load,
    deliveries_load,
    modifiers_load,
    rules_load,
)
from larpmanager.utils.io.upload.features import (
    _activate_features_from_columns,
    _get_config_from_question_type,
    _get_feature_from_question_type,
    activate_configs,
    activate_features,
)
from larpmanager.utils.io.upload.forms import (
    _get_mappings,
    _get_option,
    _get_or_create_registration_question,
    _get_or_create_writing_question,
    _options_load,
    _process_question_field,
    _questions_load,
    form_load,
)
from larpmanager.utils.io.upload.images import cover_load, get_csv_upload_tmp, normalize_profile_image
from larpmanager.utils.io.upload.parsing import (
    _get_row_name,
    _get_row_number,
    _is_blank,
    _is_missing,
    _normalize_numeric,
    _relation_value,
    _row_result,
    _skip_row_field,
    _strip_number_prefix,
    _text_to_html_paragraphs,
    _to_decimal,
    _to_int,
    invert_dict,
)
from larpmanager.utils.io.upload.registration import (
    _assign_elem,
    _reg_assign_characters,
    _reg_load,
    _registration_field_load,
    registrations_load,
)
from larpmanager.utils.io.upload.relations import (
    _assign_abilities,
    _assign_characters,
    _assign_factions,
    _assign_numeric,
    _assign_operation,
    _assign_prereq,
    _assign_relation,
    _assign_requirements,
    _assign_system,
    _assign_type,
    _resolve_exp_system,
)
from larpmanager.utils.io.upload.tickets import _ticket_load, tickets_load
from larpmanager.utils.io.upload.writing import (
    _assign_choice_answer,
    _assign_faction,
    _assign_text_answer,
    _get_mirror_instance,
    _get_questions,
    _plot_rels_load,
    _relationships_load,
    _set_assigned_member,
    _set_character_status,
    _writing_load_field,
    _writing_load_plot_rels,
    _writing_load_relationships,
    _writing_question_load,
    element_load,
    writing_load,
)

__all__ = [
    "_ability_load",
    "_ability_type_load",
    "_activate_features_from_columns",
    "_apply_ability_field",
    "_apply_criterion_field",
    "_apply_delivery_field",
    "_apply_rule_field",
    "_assign_abilities",
    "_assign_characters",
    "_assign_choice_answer",
    "_assign_elem",
    "_assign_faction",
    "_assign_factions",
    "_assign_numeric",
    "_assign_operation",
    "_assign_prereq",
    "_assign_relation",
    "_assign_requirements",
    "_assign_rule_field",
    "_assign_system",
    "_assign_text_answer",
    "_assign_type",
    "_criterion_load",
    "_delivery_load",
    "_find_delivery",
    "_free_delivery_number",
    "_get_config_from_question_type",
    "_get_feature_from_question_type",
    "_get_file",
    "_get_mappings",
    "_get_mirror_instance",
    "_get_option",
    "_get_or_create_registration_question",
    "_get_or_create_writing_question",
    "_get_questions",
    "_get_row_name",
    "_get_row_number",
    "_is_blank",
    "_is_missing",
    "_modifier_load",
    "_normalize_numeric",
    "_options_load",
    "_plot_rels_load",
    "_process_question_field",
    "_questions_load",
    "_read_uploaded_csv",
    "_reg_assign_characters",
    "_reg_load",
    "_registration_field_load",
    "_relation_value",
    "_relationships_load",
    "_resolve_exp_system",
    "_row_delivery_number",
    "_row_result",
    "_rule_load",
    "_set_assigned_member",
    "_set_character_status",
    "_skip_ability_field",
    "_skip_row_field",
    "_strip_number_prefix",
    "_text_to_html_paragraphs",
    "_ticket_load",
    "_to_decimal",
    "_to_int",
    "_writing_load_field",
    "_writing_load_plot_rels",
    "_writing_load_relationships",
    "_writing_question_load",
    "abilities_load",
    "ability_types_load",
    "activate_configs",
    "activate_features",
    "cover_load",
    "criterions_load",
    "deliveries_load",
    "element_load",
    "form_load",
    "get_csv_upload_tmp",
    "go_upload",
    "invert_dict",
    "modifiers_load",
    "normalize_profile_image",
    "registrations_load",
    "rules_load",
    "save_log",
    "tickets_load",
    "writing_load",
]
