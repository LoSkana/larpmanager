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

import os

import yaml
from django.apps import apps
from django.conf import settings as conf_settings
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ForeignKey, ManyToManyField


class Command(BaseCommand):
    help = "Reload features from yaml"

    def handle(self, *args, **options):
        """Import feature system fixtures from YAML files.

        Loads modules, features, permissions, and other system configuration
        from YAML fixtures with proper handling of foreign keys and many-to-many relations.
        """
        for fixture in [
            "module",
            "feature",
            "permission_module",
            "assoc_permission",
            "event_permission",
            "payment_methods",
            "skin",
        ]:
            fixture_path = os.path.join(conf_settings.BASE_DIR, "..", "larpmanager", "fixtures", f"{fixture}.yaml")
            with open(fixture_path, encoding="utf-8") as f:
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
            m2m_field = model._meta.get_field(field_name)
        except FieldDoesNotExist as err:
            raise ValueError(f"{field_name} not found on {model_label}") from err

        # Validate that the field is actually a many-to-many field
        if not isinstance(m2m_field, ManyToManyField):
            raise ValueError(f"{field_name} not m2m on {model_label}")

        # Get the related model and separate integer IDs from string slugs
        rel_model = m2m_field.remote_field.model
        int_ids = [v for v in values if isinstance(v, int)]
        slug_vals = [v for v in values if not isinstance(v, int)]

        # Resolve slug values to primary keys if any slugs were provided
        if slug_vals:
            qs = rel_model.objects.filter(slug__in=slug_vals).values_list("slug", "pk")
            slug_to_pk = dict(qs)

            # Check for missing slugs and raise error if any are not found
            missing = sorted(set(slug_vals) - set(slug_to_pk.keys()))
            if missing:
                raise ValueError(f"missing slugs for {model_label}.{field_name}: {', '.join(missing)}")
            resolved_from_slugs = [slug_to_pk[s] for s in slug_vals]
        else:
            resolved_from_slugs = []

        # Combine all resolved IDs and set the M2M field
        resolved_ids = int_ids + resolved_from_slugs
        getattr(instance, field_name).set(resolved_ids)

    @staticmethod
    def prepare_m2m(fields):
        m2m_fields = {}
        for key in list(fields.keys()):
            value = fields[key]
            if isinstance(value, list):
                m2m_fields[key] = value
                fields.pop(key)
        return m2m_fields

    @staticmethod
    def prepare_foreign(model, fields):
        for key in list(fields.keys()):
            try:
                # noinspection PyUnresolvedReferences, PyProtectedMember
                f = model._meta.get_field(key)
            except FieldDoesNotExist:
                continue
            if isinstance(f, ForeignKey):
                val = fields.pop(key)
                if val is None:
                    fields[f"{key}_id"] = None
                elif isinstance(val, int):
                    fields[f"{key}_id"] = val
                else:
                    rel_model = f.remote_field.model
                    rel_obj = rel_model.objects.get(slug=val)
                    fields[f"{key}_id"] = rel_obj.pk
