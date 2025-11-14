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

from pathlib import Path
from typing import Any

import yaml
from django.apps import apps
from django.conf import settings as conf_settings
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ForeignKey, ManyToManyField


class Command(BaseCommand):
    help = "Reload features from yaml"

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Import feature system fixtures from YAML files.

        Loads modules, features, permissions, and other system configuration
        from YAML fixtures with proper handling of foreign keys and many-to-many relations.
        """
        for fixture in [
            "module",
            "feature",
            "permission_module",
            "association_permission",
            "event_permission",
            "payment_methods",
            "skin",
        ]:
            fixture_path = Path(conf_settings.BASE_DIR) / ".." / "larpmanager" / "fixtures" / f"{fixture}.yaml"
            with fixture_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for obj in data:
                model_label = obj["model"]
                Model = apps.get_model(model_label)
                fields = obj["fields"]

                # set m2m
                m2m_fields = self.prepare_m2m(fields)

                # set fk
                self.prepare_foreign(Model, fields)

                # use slug, otherwise pk
                lookup = {}
                if "slug" in fields:
                    lookup["slug"] = fields["slug"]
                elif "domain" in fields:
                    lookup["domain"] = fields["domain"]
                else:
                    lookup["pk"] = obj.get("pk")

                with transaction.atomic():
                    instance, _ = Model.objects.update_or_create(defaults=fields, **lookup)

                    for field_name, values in m2m_fields.items():
                        self.set_m2m(Model, field_name, instance, model_label, values)

    @staticmethod
    def set_m2m(model: type, field_name: str, instance: object, model_label: str, values: list[int | str]) -> None:
        """Set many-to-many field values using IDs or slugs.

        Args:
            model: The Django model class containing the M2M field
            field_name: Name of the many-to-many field to set
            instance: Model instance to update
            model_label: Human-readable model name for error messages
            values: List of integer IDs or string slugs to set on the field

        Raises:
            ValueError: If field doesn't exist, isn't M2M, or slugs are missing

        """
        # Get the M2M field from the model metadata
        try:
            # noinspection PyUnresolvedReferences, PyProtectedMember
            many_to_many_field = model._meta.get_field(field_name)  # noqa: SLF001  # Django model metadata
        except FieldDoesNotExist as err:
            msg = f"{field_name} not found on {model_label}"
            raise ValueError(msg) from err

        # Validate that the field is actually a many-to-many field
        if not isinstance(many_to_many_field, ManyToManyField):
            msg = f"{field_name} not m2m on {model_label}"
            raise TypeError(msg)

        # Get the related model and separate integer IDs from string slugs
        related_model = many_to_many_field.remote_field.model
        integer_ids = [value for value in values if isinstance(value, int)]
        slug_values = [value for value in values if not isinstance(value, int)]

        # Resolve slug values to primary keys if any slugs were provided
        if slug_values:
            queryset = related_model.objects.filter(slug__in=slug_values).values_list("slug", "pk")
            slug_to_primary_key = dict(queryset)

            # Check for missing slugs and raise error if any are not found
            missing_slugs = sorted(set(slug_values) - set(slug_to_primary_key.keys()))
            if missing_slugs:
                msg = f"missing slugs for {model_label}.{field_name}: {', '.join(missing_slugs)}"
                raise ValueError(msg)
            primary_keys_from_slugs = [slug_to_primary_key[slug] for slug in slug_values]
        else:
            primary_keys_from_slugs = []

        # Combine all resolved IDs and set the M2M field
        all_primary_keys = integer_ids + primary_keys_from_slugs
        getattr(instance, field_name).set(all_primary_keys)

    @staticmethod
    def prepare_m2m(field_definitions: dict) -> dict:
        """Extract many-to-many fields from the fields dictionary.

        Args:
            field_definitions: Dictionary of field names and values

        Returns:
            Dictionary containing only the many-to-many fields (list values)

        """
        many_to_many_fields = {}
        # Iterate through a copy of keys to safely modify the original dict
        for field_name in list(field_definitions.keys()):
            field_value = field_definitions[field_name]
            # Check if value is a list (indicates m2m field)
            if isinstance(field_value, list):
                many_to_many_fields[field_name] = field_value
                field_definitions.pop(field_name)
        return many_to_many_fields

    @staticmethod
    def prepare_foreign(model: type, fields: dict) -> None:
        """Convert foreign key fields to their ID equivalents for database operations.

        Args:
            model: Django model class to check field types against.
            fields: Dictionary of field names to values, modified in-place.

        Note:
            Modifies the fields dictionary in-place, replacing ForeignKey fields
            with their corresponding _id fields.

        """
        for field_name in list(fields.keys()):
            # Check if field exists in model
            try:
                # noinspection PyUnresolvedReferences, PyProtectedMember
                field_object = model._meta.get_field(field_name)  # noqa: SLF001  # Django model metadata
            except FieldDoesNotExist:
                continue

            # Process ForeignKey fields by converting to _id format
            if isinstance(field_object, ForeignKey):
                field_value = fields.pop(field_name)

                # Handle None, int, or slug-based lookup
                if field_value is None:
                    fields[f"{field_name}_id"] = None
                elif isinstance(field_value, int):
                    fields[f"{field_name}_id"] = field_value
                else:
                    related_model = field_object.remote_field.model
                    related_object = related_model.objects.get(slug=field_value)
                    fields[f"{field_name}_id"] = related_object.pk
