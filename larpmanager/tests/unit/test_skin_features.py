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

"""Tests for the skin default-features hook on Association save."""

from django.db import transaction

from larpmanager.models.association import Association, AssociationSkin
from larpmanager.models.base import Feature
from larpmanager.tests.unit.base import BaseTestCase


class TestSkinFeatures(BaseTestCase):
    """Tests for apply_skin_features_to_association semantics."""

    def setUp(self) -> None:
        """Create a feature outside any skin's defaults and one skin default."""
        self.extra_feature = Feature.objects.create(name="Extra", slug="extra-skin-test", overall=True)
        self.default_feature = Feature.objects.create(name="Default", slug="default-skin-test", overall=True)

    def _make_skin(self, name: str) -> AssociationSkin:
        """Create a skin with an explicit pk (fixtures use hardcoded low ids)."""
        max_id = AssociationSkin.objects.order_by("-id").first().id
        skin = AssociationSkin.objects.create(id=max_id + 1, name=name, domain=f"{name}.test")
        skin.default_features.add(self.default_feature)
        return skin

    def test_new_association_keeps_features_added_in_same_transaction(self) -> None:
        """Features enabled right after creation survive the on_commit skin defaults hook.

        Demo template builders (load_demos) create an association and enable its
        features inside one transaction; the hook must add the skin defaults
        without wiping those features.
        """
        skin = self._make_skin("keepskin")

        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            association = Association.objects.create(slug="skin-keep", name="Keep", skin=skin)
            association.features.add(self.extra_feature)

        feature_ids = set(association.features.values_list("pk", flat=True))
        assert self.extra_feature.pk in feature_ids
        assert self.default_feature.pk in feature_ids

    def test_skin_change_resets_features_to_new_defaults(self) -> None:
        """Switching an existing association to another skin replaces its features."""
        old_skin = self._make_skin("oldskin")
        new_skin = self._make_skin("newskin")

        with self.captureOnCommitCallbacks(execute=True):
            association = Association.objects.create(slug="skin-switch", name="Switch", skin=old_skin)
        association.features.add(self.extra_feature)

        with self.captureOnCommitCallbacks(execute=True):
            association.skin = new_skin
            association.save()

        feature_ids = set(association.features.values_list("pk", flat=True))
        assert feature_ids == {self.default_feature.pk}
