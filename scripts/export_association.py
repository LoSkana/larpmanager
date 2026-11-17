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
# ruff: noqa: S608, T201, SLF001, E402, INP001, S105, PERF401

"""Prune a disposable copy of the database down to the data of a single association.

Run ONLY on a staging copy restored from a prod backup, never on prod:

    .venv/bin/python scripts/export_association.py --association 1 --db <staging db name> --media-out <dir> [--dry-run]

The staging database (same server and credentials as settings) must have "export" in its name. All changes run in one transaction; FK constraints
(deferred by Django) are checked before commit, so any orphan aborts the whole run.
Afterwards: pg_dump the staging database and ship it together with the media folder.
"""

import argparse
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

import django

django.setup()

from django.apps import apps
from django.conf import settings
from django.db import connection, models, transaction

# Tables emptied entirely: logs, sessions, queues, platform data, credentials and anything re-creatable
DROP = {
    "admin.LogEntry",
    "sessions.Session",
    "background_task.Task",
    "background_task.CompletedTask",
    "ipn.PayPalIPN",
    "account.EmailConfirmation",
    "socialaccount.SocialApp",
    "socialaccount.SocialToken",
    "axes.AccessFailureLog",
    "axes.AccessAttempt",
    "axes.AccessAttemptExpiration",
    "axes.AccessLog",
    "otp_totp.TOTPDevice",
    "otp_static.StaticDevice",
    "otp_static.StaticToken",
    "auth.Group",
    "auth.Group_permissions",
    "auth.User_groups",
    "auth.User_user_permissions",
    "larpmanager.Log",
    "larpmanager.Config",
    "larpmanager.PublisherApiKey",
    "larpmanager.NotificationQueue",
    "larpmanager.ChatMessage",
    "larpmanager.Contact",
    "larpmanager.EmailContent",
    "larpmanager.EmailRecipient",
    "larpmanager.EmailSuppression",
    "larpmanager.TextVersion",
    "larpmanager.RoleInvite",
    "larpmanager.OneTimeAccessToken",
    "socialaccount.SocialAccount",
}
DROP_PREFIXES = ("larpmanager.LarpManager",)

# Platform-wide tables required by the schema, kept as they are
GLOBAL = {
    "contenttypes.ContentType",
    "auth.Permission",
    "larpmanager.FeatureModule",
    "larpmanager.Feature",
    "larpmanager.Feature_dependencies",
    "larpmanager.PaymentMethod",
    "larpmanager.PermissionModule",
    "larpmanager.AssociationPermission",
    "larpmanager.EventPermission",
}

# Tables pruned by an explicit rule instead of an owner FK
ROOT = {"larpmanager.Association", "larpmanager.AssociationSkin"}
MEMBER = {"larpmanager.Member", "auth.User"}
# Tables owned only by a member or user, pruned together with them
MEMBER_ATTACHED = {"larpmanager.MemberConfig", "account.EmailAddress"}

# Member columns left untouched when anonymizing an account
ANONYMIZE_KEEP = {
    "id",
    "uuid",
    "created",
    "updated",
    "deleted",
    "deleted_by_cascade",
    "media_token",
    "user_id",
    "parent_id",
}

UNMANAGED_TABLES = {"django_migrations"}

# QuestionApplicable value -> model holding the element referenced by WritingAnswer/WritingChoice.element_id
APPLICABLE_MODELS = {
    "c": "larpmanager.Character",
    "p": "larpmanager.Plot",
    "f": "larpmanager.Faction",
    "q": "larpmanager.Quest",
    "t": "larpmanager.Trait",
    "r": "larpmanager.Prologue",
    "g": "larpmanager.Guild",
}

SECRET_CONFIG_RE = r"(password|secret|api_?key)"
CONFIG_MODELS = (
    "larpmanager.AssociationConfig",
    "larpmanager.EventConfig",
    "larpmanager.RunConfig",
    "larpmanager.CharacterConfig",
    "larpmanager.MemberConfig",
)
FILE_TYPES = ("FileField", "ImageField")


def qn(name: str) -> str:
    """Quote an SQL identifier."""
    return connection.ops.quote_name(name)


def label(model: type[models.Model]) -> str:
    """Return app_label.ModelName, including auto-created M2M through models."""
    return f"{model._meta.app_label}.{model._meta.object_name}"


def run(sql: str, params: list | None = None) -> int:
    """Execute a statement and return the affected row count."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.rowcount


def fetch(sql: str, params: list | None = None) -> list[tuple]:
    """Execute a query and return all rows."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchall()


class Schema:
    """Classification of every model into drop / global / pruned groups."""

    def __init__(self) -> None:
        """Load all models and validate that each one is classified."""
        self.models = {label(m): m for m in apps.get_models(include_auto_created=True)}
        self.drop = {lb for lb in self.models if lb in DROP or lb.startswith(DROP_PREFIXES)}
        self.pruned = set(self.models) - self.drop - GLOBAL
        self.scoped = self.pruned - ROOT - MEMBER - MEMBER_ATTACHED
        self.validate()

    def fks(self, lb: str) -> list[models.Field]:
        """Return the concrete FK fields of a model."""
        return [f for f in self.models[lb]._meta.concrete_fields if f.is_relation]

    def target(self, field: models.Field) -> str:
        """Return the label of the model a FK points to."""
        return label(field.related_model)

    def owner_fks(self, lb: str) -> list[models.Field]:
        """Return FKs that tie a row to the association (to root or scoped tables)."""
        return [f for f in self.fks(lb) if self.target(f) in ROOT | self.scoped]

    def table(self, lb: str) -> str:
        """Return the db table of a model."""
        return self.models[lb]._meta.db_table

    def validate(self) -> None:
        """Fail on unknown tables, unowned scoped models, or kept rows pointing to dropped tables."""
        errors = []
        for lb in sorted(DROP | GLOBAL | ROOT | MEMBER | MEMBER_ATTACHED):
            if lb not in self.models:
                errors.append(f"configured model not found: {lb}")
        for lb in sorted(self.scoped):
            if not self.owner_fks(lb):
                errors.append(f"unclassified model (no owner FK): {lb}")
        for lb in sorted(self.pruned | GLOBAL):
            errors.extend(
                f"{lb}.{f.name} is a non-nullable FK to dropped {self.target(f)}"
                for f in self.fks(lb)
                if self.target(f) in self.drop and not f.null
            )
        model_tables = {m._meta.db_table for m in self.models.values()}
        errors.extend(
            f"table without model: {t}"
            for t in sorted(set(connection.introspection.table_names()) - model_tables - UNMANAGED_TABLES)
        )
        if errors:
            sys.exit("Schema check failed:\n  " + "\n  ".join(errors))


def drop_tables(schema: Schema) -> None:
    """Null references to dropped tables, then empty them."""
    for lb in sorted(schema.pruned | GLOBAL):
        for f in schema.fks(lb):
            if schema.target(f) in schema.drop:
                run(f"UPDATE {qn(schema.table(lb))} SET {qn(f.column)} = NULL WHERE {qn(f.column)} IS NOT NULL")
    for lb in sorted(schema.drop):
        n = run(f"DELETE FROM {qn(schema.table(lb))}")
        print(f"drop {lb}: {n}")


def delete_soft_deleted(schema: Schema) -> None:
    """Hard-delete every soft-deleted row."""
    for lb in sorted(schema.pruned | GLOBAL):
        if any(f.column == "deleted" for f in schema.models[lb]._meta.concrete_fields):
            n = run(f"DELETE FROM {qn(schema.table(lb))} WHERE deleted IS NOT NULL")
            if n:
                print(f"soft-deleted {lb}: {n}")


def filter_roots(schema: Schema, association_id: int) -> None:
    """Keep only the association, its skin, and rows of other tables owned by it."""
    run(f"DELETE FROM {qn(schema.table('larpmanager.Association'))} WHERE id <> %s", [association_id])
    association_table = qn(schema.table("larpmanager.Association"))
    run(
        f"DELETE FROM {qn(schema.table('larpmanager.AssociationSkin'))} "
        f"WHERE id NOT IN (SELECT skin_id FROM {association_table})"
    )
    for lb in sorted(schema.scoped | MEMBER_ATTACHED):
        for f in schema.fks(lb):
            if schema.target(f) == "larpmanager.Association":
                col = qn(f.column)
                run(f"DELETE FROM {qn(schema.table(lb))} WHERE {col} IS NULL OR {col} <> %s", [association_id])


def prune_orphans(schema: Schema) -> int:
    """Apply on_delete semantics to rows pointing at removed rows; return the number of changed rows."""
    changed = 0
    for lb in sorted(schema.pruned | GLOBAL):
        table = qn(schema.table(lb))
        for f in schema.fks(lb):
            target = schema.target(f)
            if target not in schema.pruned | GLOBAL:
                continue
            target_table = qn(schema.table(target))
            target_col = qn(f.target_field.column)
            col = qn(f.column)
            orphan = (
                f"{col} IS NOT NULL AND NOT EXISTS "
                f"(SELECT 1 FROM {target_table} tgt WHERE tgt.{target_col} = {table}.{col})"
            )
            if f.remote_field.on_delete is models.SET_NULL:
                changed += run(f"UPDATE {table} SET {col} = NULL WHERE {orphan}")
            else:
                changed += run(f"DELETE FROM {table} WHERE {orphan}")
        owners = schema.owner_fks(lb) if lb in schema.scoped else []
        if owners and all(f.null for f in owners):
            unowned = " AND ".join(f"{qn(f.column)} IS NULL" for f in owners)
            changed += run(f"DELETE FROM {table} WHERE {unowned}")
    changed += prune_writing_elements(schema)
    return changed


def prune_writing_elements(schema: Schema) -> int:
    """Delete writing answers and choices whose generic element no longer exists."""
    changed = 0
    question_table = qn(schema.table("larpmanager.WritingQuestion"))
    for lb in ("larpmanager.WritingAnswer", "larpmanager.WritingChoice"):
        table = qn(schema.table(lb))
        for applicable, element_lb in APPLICABLE_MODELS.items():
            changed += run(
                f"DELETE FROM {table} WHERE question_id IN "
                f"(SELECT id FROM {question_table} WHERE applicable = %s) "
                f"AND NOT EXISTS (SELECT 1 FROM {qn(schema.table(element_lb))} el WHERE el.id = {table}.element_id)",
                [applicable],
            )
    return changed


def prune_until_stable(schema: Schema) -> None:
    """Repeat orphan pruning until nothing changes."""
    while True:
        changed = prune_orphans(schema)
        print(f"orphan pass: {changed}")
        if not changed:
            return


def prune_members(schema: Schema, association_id: int) -> None:
    """Keep members with a membership or referenced by kept rows (plus their parent accounts), and their users."""
    member_table = qn(schema.table("larpmanager.Member"))
    run("CREATE TEMP TABLE keep_member (id integer PRIMARY KEY) ON COMMIT DROP")
    run(
        f"INSERT INTO keep_member SELECT DISTINCT member_id FROM {qn(schema.table('larpmanager.Membership'))} "
        f"WHERE association_id = %s ON CONFLICT DO NOTHING",
        [association_id],
    )
    for lb in sorted(schema.scoped | ROOT):
        for f in schema.fks(lb):
            if schema.target(f) == "larpmanager.Member":
                col = qn(f.column)
                run(
                    f"INSERT INTO keep_member SELECT DISTINCT {col} FROM {qn(schema.table(lb))} "
                    f"WHERE {col} IS NOT NULL ON CONFLICT DO NOTHING"
                )
    while run(
        f"INSERT INTO keep_member SELECT DISTINCT m.parent_id FROM {member_table} m "
        f"JOIN keep_member k ON k.id = m.id WHERE m.parent_id IS NOT NULL ON CONFLICT DO NOTHING"
    ):
        pass
    print(f"members kept: {fetch('SELECT count(*) FROM keep_member')[0][0]}")
    run(f"DELETE FROM {member_table} WHERE id NOT IN (SELECT id FROM keep_member)")
    user_table = qn(schema.table("auth.User"))
    run(f"DELETE FROM {user_table} WHERE id NOT IN (SELECT user_id FROM {member_table})")
    anonymize_members(schema, association_id)
    run(f"UPDATE {user_table} SET is_staff = false, is_superuser = false")


def anonymize_members(schema: Schema, association_id: int) -> None:
    """Strip personal data and login from platform staff and from members without a membership."""
    member_table = qn(schema.table("larpmanager.Member"))
    user_table = qn(schema.table("auth.User"))
    membership_table = qn(schema.table("larpmanager.Membership"))
    ids = [
        r[0]
        for r in fetch(
            f"SELECT m.id FROM {member_table} m JOIN {user_table} u ON u.id = m.user_id "
            f"WHERE u.is_staff OR u.is_superuser OR NOT EXISTS "
            f"(SELECT 1 FROM {membership_table} ms WHERE ms.member_id = m.id AND ms.association_id = %s)",
            [association_id],
        )
    ]
    print(f"members anonymized: {ids}")
    if not ids:
        return
    assignments = []
    for f in schema.models["larpmanager.Member"]._meta.concrete_fields:
        if f.column in ANONYMIZE_KEEP or f.column in ("email", "name"):
            continue
        if f.null:
            assignments.append(f"{qn(f.column)} = NULL")
        elif f.get_internal_type() in ("CharField", "TextField", *FILE_TYPES):
            assignments.append(f"{qn(f.column)} = ''")
    assignments += ["email = 'removed-' || id || '@invalid'", "name = 'Removed'"]
    run(f"UPDATE {member_table} SET {', '.join(assignments)} WHERE id = ANY(%s)", [ids])
    user_ids = f"(SELECT user_id FROM {member_table} WHERE id = ANY(%s))"
    run(
        f"UPDATE {user_table} SET password = '!', username = 'removed-' || id, email = 'removed-' || id || '@invalid', "
        f"first_name = '', last_name = '' WHERE id IN {user_ids}",
        [ids],
    )
    run(f"DELETE FROM {qn(schema.table('account.EmailAddress'))} WHERE user_id IN {user_ids}", [ids])
    run(f"DELETE FROM {qn(schema.table('larpmanager.MemberConfig'))} WHERE member_id = ANY(%s)", [ids])


def scrub(schema: Schema, association_id: int) -> None:
    """Remove secrets and data keyed to other associations."""
    run(f"UPDATE {qn(schema.table('larpmanager.Association'))} SET key = NULL")
    run(f"UPDATE {qn(schema.table('larpmanager.Membership'))} SET password_reset = ''")
    for lb in CONFIG_MODELS:
        n = run(f"DELETE FROM {qn(schema.table(lb))} WHERE name ~* %s", [SECRET_CONFIG_RE])
        print(f"secret configs removed from {lb}: {n}")
    n = run(
        f"DELETE FROM {qn(schema.table('larpmanager.MemberConfig'))} WHERE name = 'sticky' "
        f"OR (name ~ '^(flag|membership_fee_pending)_[0-9]+_' "
        f"AND name !~ %s)",
        [f"^(flag|membership_fee_pending)_{association_id}_"],
    )
    print(f"member configs removed: {n}")
    names = fetch(
        f"SELECT regexp_replace(name, '[0-9]+', 'N', 'g') AS n, count(*) "
        f"FROM {qn(schema.table('larpmanager.MemberConfig'))} GROUP BY n ORDER BY n"
    )
    print("member config names left: " + ", ".join(f"{n} ({c})" for n, c in names))


def verify(schema: Schema, association_id: int) -> None:
    """Check FK integrity and that no row of another association survives."""
    run("SET CONSTRAINTS ALL IMMEDIATE")
    errors = []
    for lb in sorted(schema.pruned):
        for f in schema.fks(lb):
            if schema.target(f) == "larpmanager.Association":
                col = qn(f.column)
                n = fetch(f"SELECT count(*) FROM {qn(schema.table(lb))} WHERE {col} <> %s", [association_id])[0][0]
                if n:
                    errors.append(f"{lb}: {n} rows of other associations")
    if errors:
        raise RuntimeError("Verification failed:\n  " + "\n  ".join(errors))
    for lb in sorted(set(schema.models) - schema.drop):
        n = fetch(f"SELECT count(*) FROM {qn(schema.table(lb))}")[0][0]
        print(f"rows {lb}: {n}")


def collect_media(schema: Schema, media_out: Path) -> None:
    """Copy files referenced by kept rows (file fields and media URLs inside text) to media_out."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    media_url_re = re.compile(re.escape(settings.MEDIA_URL) + r"([^\"'\s()<>?#]+)")
    paths = set()
    for lb in sorted(set(schema.models) - schema.drop):
        table = qn(schema.table(lb))
        for f in schema.models[lb]._meta.concrete_fields:
            kind = f.get_internal_type()
            col = qn(f.column)
            if kind in FILE_TYPES:
                paths.update(r[0] for r in fetch(f"SELECT {col} FROM {table} WHERE {col} <> ''"))
            elif kind == "TextField":
                rows = fetch(f"SELECT {col} FROM {table} WHERE {col} LIKE %s", [f"%{settings.MEDIA_URL}%"])
                for (text,) in rows:
                    paths.update(media_url_re.findall(text))
    missing = defaultdict(int)
    copied = 0
    for rel in sorted(paths):
        src = (media_root / rel).resolve()
        if not src.is_relative_to(media_root) or not src.is_file():
            missing[rel.split("/")[0]] += 1
            continue
        dst = media_out / src.relative_to(media_root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"media copied: {copied}, missing by folder: {dict(missing)}")


def main() -> None:
    """Parse arguments and run the export pruning."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--association", type=int, required=True)
    parser.add_argument("--db", required=True, help="Staging database name, must contain 'export'")
    parser.add_argument("--media-out", type=Path, help="Folder to copy referenced media files to")
    parser.add_argument("--dry-run", action="store_true", help="Roll back at the end")
    args = parser.parse_args()

    db_name = args.db
    if "export" not in db_name:
        sys.exit(f"Refusing to run on database '{db_name}': use a staging copy whose name contains 'export'")
    connection.settings_dict["NAME"] = db_name
    if args.media_out and args.media_out.exists() and any(args.media_out.iterdir()):
        sys.exit(f"{args.media_out} is not empty")

    schema = Schema()
    with transaction.atomic():
        drop_tables(schema)
        delete_soft_deleted(schema)
        filter_roots(schema, args.association)
        prune_until_stable(schema)
        prune_members(schema, args.association)
        prune_until_stable(schema)
        scrub(schema, args.association)
        verify(schema, args.association)
        if args.media_out:
            collect_media(schema, args.media_out)
        if args.dry_run:
            transaction.set_rollback(True)
            print("dry run: rolled back")
            return
    print(f"done. next: pg_dump --no-owner --no-privileges -Fc {db_name} > association_{args.association}.dump")


if __name__ == "__main__":
    main()
