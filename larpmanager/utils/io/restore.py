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

import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from larpmanager.models.base import Feature
from larpmanager.models.casting import QuestType
from larpmanager.models.event import EventConfig, RunConfig
from larpmanager.models.experience import AbilityExp
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.writing import Character, CharacterConfig, Plot, PlotCharacterRel, Relationship
from larpmanager.utils.io.upload import (
    abilities_load,
    form_load,
    registrations_load,
    tickets_load,
    writing_load,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers: fake file/form objects to reuse existing upload functions
# ---------------------------------------------------------------------------


class _FakeFile:
    """Wrap raw bytes to mimic a Django UploadedFile for existing load functions."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.size = len(data)

    def seek(self, n: int) -> int:
        return self._buf.seek(n)

    def read(self) -> bytes:
        return self._buf.read()


class _FakeForm:
    """Mimic a validated Django Form with cleaned_data for existing load functions."""

    def __init__(self, first: _FakeFile | None = None, second: _FakeFile | None = None) -> None:
        self.cleaned_data: dict[str, _FakeFile | None] = {"first": first, "second": second}


# ---------------------------------------------------------------------------
# Temp storage: save/load the uploaded ZIP between preview and confirm steps
# ---------------------------------------------------------------------------

_TMP_DIR_NAME = "tmp_restore"


def save_restore_temp(zip_bytes: bytes) -> str:
    """Save ZIP bytes to a temp file, return the unique key."""
    key = str(uuid.uuid4())
    path = Path(settings.MEDIA_ROOT) / _TMP_DIR_NAME / f"{key}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zip_bytes)
    return key


def load_restore_temp(key: str) -> bytes | None:
    """Load and delete the temp ZIP file; returns None if expired/missing."""
    path = Path(settings.MEDIA_ROOT) / _TMP_DIR_NAME / f"{key}.zip"
    if not path.exists():
        return None
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_df(zip_file: zipfile.ZipFile, filename: str) -> pd.DataFrame | None:
    """Read a CSV from the open ZipFile, return DataFrame or None."""
    try:
        raw = zip_file.read(filename)
        df = pd.read_csv(io.BytesIO(raw), dtype=str).fillna("")
        df.columns = [c.lower().strip() for c in df.columns]
    except Exception:
        logger.exception("Failed to read %s from ZIP", filename)
        return None
    else:
        return df


def _section(label: str, creates: list, updates: list, skips: list) -> dict:
    return {"label": label, "creates": creates, "updates": updates, "skips": skips}


def _fake_csv(df: pd.DataFrame) -> _FakeFile:
    """Serialize a DataFrame back to CSV bytes wrapped in _FakeFile."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return _FakeFile(buf.getvalue().encode("utf-8"))


# ---------------------------------------------------------------------------
# Preview functions: read-only, return section dicts
# ---------------------------------------------------------------------------


def _preview_configuration(context: dict, df: pd.DataFrame) -> dict:
    event = context["event"]
    run = context["run"]
    if "source" not in df.columns:
        df["source"] = "event"

    event_names = set(EventConfig.objects.filter(event=event, deleted__isnull=True).values_list("name", flat=True))
    run_names = set(RunConfig.objects.filter(run=run, deleted__isnull=True).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        source = str(row.get("source", "event")).strip()
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        if source == "event":
            (updates if name in event_names else creates).append(f"event / {name}")
        elif source == "run":
            (updates if name in run_names else creates).append(f"run / {name}")
        else:
            skips.append(f"{source} / {name}")

    return _section(str(_("Configuration")), creates, updates, skips)


def _preview_features(context: dict, df: pd.DataFrame) -> dict:
    event = context["event"]
    if "source" not in df.columns:
        df["source"] = "event"

    existing = set(event.features.values_list("slug", flat=True))
    known_slugs = set(Feature.objects.values_list("slug", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        source = str(row.get("source", "event")).strip()
        if source != "event":
            skips.append(f"{row.get('name', '')} ({row.get('slug', '')}) [association]")
            continue
        slug = str(row.get("slug", "")).strip()
        name = str(row.get("name", slug)).strip()
        label = f"{name} ({slug})"
        if slug in existing:
            skips.append(label)
        elif slug in known_slugs:
            creates.append(label)
        else:
            skips.append(f"WARN {label}: feature not found in system")

    return _section(str(_("Features")), creates, updates, skips)


def _preview_tickets(context: dict, df: pd.DataFrame) -> dict:
    event = context["event"]
    existing = set(event.get_elements(RegistrationTicket).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        (updates if name in existing else creates).append(name)

    return _section(str(_("Tickets")), creates, updates, skips)


def _preview_registration_form(context: dict, df_q: pd.DataFrame, df_o: pd.DataFrame | None) -> dict:
    event = context["event"]
    existing_q = set(event.get_elements(RegistrationQuestion).values_list("name", flat=True))
    existing_o = set(event.get_elements(RegistrationOption).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df_q.iterrows():
        name = str(row.get("name", "")).strip()
        if name:
            (updates if name in existing_q else creates).append(f"Q: {name}")
    if df_o is not None:
        for _idx, row in df_o.iterrows():
            name = str(row.get("name", "")).strip()
            if name:
                (updates if name in existing_o else creates).append(f"Opt: {name}")

    return _section(str(_("Registration Form")), creates, updates, skips)


def _preview_character_form(context: dict, df_q: pd.DataFrame, df_o: pd.DataFrame | None) -> dict:
    event = context["event"]
    existing_q = set(event.get_elements(WritingQuestion).values_list("name", flat=True))
    existing_o = set(event.get_elements(WritingOption).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df_q.iterrows():
        name = str(row.get("name", "")).strip()
        if name:
            (updates if name in existing_q else creates).append(f"Q: {name}")
    if df_o is not None:
        for _idx, row in df_o.iterrows():
            name = str(row.get("name", "")).strip()
            if name:
                (updates if name in existing_o else creates).append(f"Opt: {name}")

    return _section(str(_("Character Form")), creates, updates, skips)


def _preview_character_config(context: dict, df: pd.DataFrame) -> dict:
    event_id = context["event"].get_class_parent(Character)
    char_map = {c.number: c.id for c in Character.objects.filter(event_id=event_id, deleted__isnull=True)}
    existing = set(
        CharacterConfig.objects.filter(character__event_id=event_id, deleted__isnull=True).values_list(
            "character__number", "name"
        )
    )

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        try:
            num = int(str(row.get("character_number", "")).strip())
        except ValueError:
            skips.append(f"invalid number: {row.get('character_number', '')}")
            continue
        name = str(row.get("name", "")).strip()
        if num not in char_map:
            skips.append(f"character #{num} not found")
            continue
        (updates if (num, name) in existing else creates).append(f"#{num} / {name}")

    return _section(str(_("Character Config")), creates, updates, skips)


def _preview_writing(context: dict, df: pd.DataFrame, typ: str) -> dict:
    model_class = QuestionApplicable.get_applicable_inverse(QuestionApplicable.get_applicable(typ))
    if model_class is None:
        return _section(typ.title(), [], [], [f"unsupported type: {typ}"])

    event_id = context["event"].get_class_parent(model_class)
    existing = set(model_class.objects.filter(event_id=event_id, deleted__isnull=True).values_list("number", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        try:
            num = int(str(row.get("number", "")).strip())
        except ValueError:
            skips.append(f"invalid number: {row.get('number', '')}")
            continue
        name = str(row.get("name", f"#{num}")).strip()
        (updates if num in existing else creates).append(f"#{num} {name}")

    return _section(typ.title(), creates, updates, skips)


def _preview_questtype(context: dict, df: pd.DataFrame) -> dict:
    event_id = context["event"].get_class_parent(QuestType)
    existing = set(QuestType.objects.filter(event_id=event_id, deleted__isnull=True).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if name:
            (updates if name in existing else creates).append(name)

    return _section("Quest Type", creates, updates, skips)


def _preview_abilities(context: dict, df: pd.DataFrame) -> dict:
    event_id = context["event"].get_class_parent(AbilityExp)
    existing = set(AbilityExp.objects.filter(event_id=event_id, deleted__isnull=True).values_list("name", flat=True))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if name:
            (updates if name in existing else creates).append(name)

    return _section(str(_("Abilities")), creates, updates, skips)


def _preview_registration(context: dict, df: pd.DataFrame) -> dict:
    run = context["run"]
    existing_emails = set(
        Registration.objects.filter(run=run, cancellation_date__isnull=True)
        .select_related("member__user")
        .values_list("member__user__email", flat=True)
    )

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        email = str(row.get("email", "")).strip().lower()
        if not email:
            continue
        if not User.objects.filter(email__iexact=email).exists():
            skips.append(f"{email}: user not found")
        elif email in {e.lower() for e in existing_emails}:
            updates.append(email)
        else:
            creates.append(email)

    return _section(str(_("Registrations")), creates, updates, skips)


def _preview_plot_rels(context: dict, df: pd.DataFrame) -> dict:
    event_id = context["event"].get_class_parent(Plot)
    existing = set(
        PlotCharacterRel.objects.filter(plot__event_id=event_id).values_list("plot__name", "character__name")
    )

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        plot = str(row.get("plot", "")).strip()
        char = str(row.get("character", "")).strip()
        if plot and char:
            (updates if (plot, char) in existing else creates).append(f"{plot} / {char}")

    return _section(str(_("Plot Roles")), creates, updates, skips)


def _preview_relationships(context: dict, df: pd.DataFrame) -> dict:
    event_id = context["event"].get_class_parent(Character)
    existing = set(Relationship.objects.filter(source__event_id=event_id).values_list("source__name", "target__name"))

    creates, updates, skips = [], [], []
    for _idx, row in df.iterrows():
        src = str(row.get("source", "")).strip()
        tgt = str(row.get("target", "")).strip()
        if src and tgt:
            (updates if (src, tgt) in existing else creates).append(f"{src} -> {tgt}")

    return _section(str(_("Relationships")), creates, updates, skips)


# ---------------------------------------------------------------------------
# Execute functions: delegate to existing upload functions via FakeFile/FakeForm
# ---------------------------------------------------------------------------


def _exec_configuration(context: dict, df: pd.DataFrame) -> list[str]:
    event = context["event"]
    run = context["run"]
    if "source" not in df.columns:
        df["source"] = "event"

    logs: list[str] = []
    for _idx, row in df.iterrows():
        source = str(row.get("source", "event")).strip()
        name = str(row.get("name", "")).strip()
        value = str(row.get("value", "")).strip()
        if not name:
            continue
        if source == "event":
            try:
                cfg = EventConfig.objects.get(event=event, name=name, deleted__isnull=True)
                cfg.value = value
                cfg.save()
                logs.append(f"OK - Updated event config: {name}")
            except EventConfig.DoesNotExist:
                EventConfig.objects.create(event=event, name=name, value=value)
                logs.append(f"OK - Created event config: {name}")
        elif source == "run":
            try:
                cfg = RunConfig.objects.get(run=run, name=name, deleted__isnull=True)
                cfg.value = value
                cfg.save()
                logs.append(f"OK - Updated run config: {name}")
            except RunConfig.DoesNotExist:
                RunConfig.objects.create(run=run, name=name, value=value)
                logs.append(f"OK - Created run config: {name}")
        else:
            logs.append(f"SKIP - {source} config (read-only): {name}")
    return logs


def _exec_features(context: dict, df: pd.DataFrame) -> list[str]:
    event = context["event"]
    if "source" not in df.columns:
        df["source"] = "event"

    existing = set(event.features.values_list("slug", flat=True))
    logs: list[str] = []
    for _idx, row in df.iterrows():
        source = str(row.get("source", "event")).strip()
        if source != "event":
            logs.append(f"SKIP - association feature: {row.get('slug', '')}")
            continue
        slug = str(row.get("slug", "")).strip()
        if not slug:
            continue
        if slug in existing:
            logs.append(f"SKIP - feature already present: {slug}")
            continue
        try:
            feature = Feature.objects.get(slug=slug)
            event.features.add(feature)
            logs.append(f"OK - Added feature: {slug}")
        except Feature.DoesNotExist:
            logs.append(f"ERR - Feature not found in system: {slug}")
    return logs


def _exec_character_config(context: dict, df: pd.DataFrame) -> list[str]:
    event_id = context["event"].get_class_parent(Character)
    char_map = {c.number: c for c in Character.objects.filter(event_id=event_id, deleted__isnull=True)}

    logs: list[str] = []
    for _idx, row in df.iterrows():
        try:
            num = int(str(row.get("character_number", "")).strip())
        except ValueError:
            logs.append(f"ERR - invalid character_number: {row.get('character_number', '')}")
            continue
        name = str(row.get("name", "")).strip()
        value = str(row.get("value", "")).strip()
        char = char_map.get(num)
        if char is None:
            logs.append(f"ERR - character #{num} not found")
            continue
        try:
            cfg = CharacterConfig.objects.get(character=char, name=name, deleted__isnull=True)
            cfg.value = value
            cfg.save()
            logs.append(f"OK - Updated character #{num} config: {name}")
        except CharacterConfig.DoesNotExist:
            CharacterConfig.objects.create(character=char, name=name, value=value)
            logs.append(f"OK - Created character #{num} config: {name}")
    return logs


def _exec_questtype(context: dict, df: pd.DataFrame) -> list[str]:
    event_id = context["event"].get_class_parent(QuestType)
    event = context["event"]
    logs: list[str] = []
    for _idx, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        try:
            num = int(str(row.get("number", "")).strip())
        except ValueError:
            num = None
        if num is not None:
            qt, created = QuestType.objects.get_or_create(
                event_id=event_id, number=num, deleted__isnull=True, defaults={"name": name, "event": event}
            )
            if not created and qt.name != name:
                qt.name = name
                qt.save()
            logs.append(f"{'OK - Created' if created else 'OK - Updated'} quest type: {name}")
        else:
            qt, created = QuestType.objects.get_or_create(
                event_id=event_id, name=name, deleted__isnull=True, defaults={"event": event}
            )
            logs.append(f"{'OK - Created' if created else 'OK - Exists'} quest type: {name}")
    return logs


def _exec_writing(context: dict, df_main: pd.DataFrame, typ: str, df_second: pd.DataFrame | None = None) -> list[str]:
    """Delegate to writing_load via FakeFile/FakeForm."""
    ctx = {**context, "typ": typ}
    first_file = _fake_csv(df_main)
    second_file = _fake_csv(df_second) if df_second is not None else None
    return writing_load(ctx, _FakeForm(first=first_file, second=second_file))


def _exec_registration_form(
    context: dict, df_q: pd.DataFrame, df_o: pd.DataFrame | None, *, is_registration: bool
) -> list[str]:
    typ = "registration_form" if is_registration else "character_form"
    ctx = {**context, "typ": typ}
    q_file = _fake_csv(df_q)
    o_file = _fake_csv(df_o) if df_o is not None else None
    return form_load(ctx, _FakeForm(first=q_file, second=o_file), is_registration=is_registration)


def _exec_tickets(context: dict, df: pd.DataFrame) -> list[str]:
    ctx = {**context, "typ": "registration_ticket"}
    return tickets_load(ctx, _FakeForm(first=_fake_csv(df)))


def _exec_abilities(context: dict, df: pd.DataFrame) -> list[str]:
    ctx = {**context, "typ": "exp_abilitie"}
    return abilities_load(ctx, _FakeForm(first=_fake_csv(df)))


def _exec_registration(context: dict, df: pd.DataFrame) -> list[str]:
    ctx = {**context, "typ": "registration"}
    return registrations_load(ctx, _FakeForm(first=_fake_csv(df)))


# ---------------------------------------------------------------------------
# ZIP parsing: build filename -> DataFrame mapping
# ---------------------------------------------------------------------------

_WRITING_TYPES = {"character", "faction", "plot", "quest", "trait", "prologue"}


def _parse_zip(zip_bytes: bytes) -> dict[str, pd.DataFrame]:
    """Open ZIP and return {stem: DataFrame} for every .csv file found."""
    dfs: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith(".csv"):
                continue
            stem = Path(info.filename).stem.lower()
            df = _read_df(z, info.filename)
            if df is not None and not df.empty:
                dfs[stem] = df
    return dfs


# ---------------------------------------------------------------------------
# Preview helpers to keep preview_restore under complexity limit
# ---------------------------------------------------------------------------


def _preview_writing_types(
    context: dict, dfs: dict[str, pd.DataFrame], sections: list[dict], handled: set[str]
) -> None:
    for typ in _WRITING_TYPES:
        if typ not in dfs:
            continue
        sec = _preview_writing(context, dfs[typ], typ)
        if typ == "character" and "relationships" in dfs:
            rels = _preview_relationships(context, dfs["relationships"])
            sec["creates"] += rels["creates"]
            sec["updates"] += rels["updates"]
            sec["skips"] += rels["skips"]
            handled.add("relationships")
        if typ == "plot" and "plot_rels" in dfs:
            pr = _preview_plot_rels(context, dfs["plot_rels"])
            sec["creates"] += pr["creates"]
            sec["updates"] += pr["updates"]
            sec["skips"] += pr["skips"]
            handled.add("plot_rels")
        sections.append(sec)
        handled.add(typ)


def _preview_form_sections(
    context: dict, dfs: dict[str, pd.DataFrame], sections: list[dict], handled: set[str]
) -> None:
    if "registration_questions" in dfs:
        sec = _preview_registration_form(context, dfs["registration_questions"], dfs.get("registration_options"))
        sections.append(sec)
        handled.add("registration_questions")
        handled.add("registration_options")
    if "writing_questions" in dfs:
        sec = _preview_character_form(context, dfs["writing_questions"], dfs.get("writing_options"))
        sections.append(sec)
        handled.add("writing_questions")
        handled.add("writing_options")


# ---------------------------------------------------------------------------
# Public API: preview_restore and execute_restore
# ---------------------------------------------------------------------------


def preview_restore(context: dict, zip_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse ZIP and return (sections, unknown_files) without modifying the DB."""
    dfs = _parse_zip(zip_bytes)
    sections: list[dict] = []
    handled: set[str] = set()

    if "configuration" in dfs:
        sections.append(_preview_configuration(context, dfs["configuration"]))
        handled.add("configuration")

    if "features" in dfs:
        sections.append(_preview_features(context, dfs["features"]))
        handled.add("features")

    if "tickets" in dfs:
        sections.append(_preview_tickets(context, dfs["tickets"]))
        handled.add("tickets")

    _preview_form_sections(context, dfs, sections, handled)

    if "character_config" in dfs:
        sections.append(_preview_character_config(context, dfs["character_config"]))
        handled.add("character_config")

    if "registration" in dfs:
        sections.append(_preview_registration(context, dfs["registration"]))
        handled.add("registration")

    _preview_writing_types(context, dfs, sections, handled)

    if "questtype" in dfs:
        sections.append(_preview_questtype(context, dfs["questtype"]))
        handled.add("questtype")

    if "abilities" in dfs:
        sections.append(_preview_abilities(context, dfs["abilities"]))
        handled.add("abilities")

    unknown = [f"{stem}.csv" for stem in dfs if stem not in handled]
    return sections, unknown


def _safe_run(logs: list[str], label: str, fn: Any, *args: Any) -> None:
    try:
        logs.extend(fn(*args))
    except Exception as exc:
        logger.exception("Restore error in %s", label)
        logs.append(f"ERR - {label}: {exc}")


def _exec_writing_types(context: dict, dfs: dict[str, pd.DataFrame], logs: list[str]) -> None:
    for typ in _WRITING_TYPES:
        if typ not in dfs:
            continue
        second = dfs.get("relationships") if typ == "character" else dfs.get("plot_rels") if typ == "plot" else None
        _safe_run(logs, typ, _exec_writing, context, dfs[typ], typ, second)


def _exec_form_sections(context: dict, dfs: dict[str, pd.DataFrame], logs: list[str]) -> None:
    if "registration_questions" in dfs:
        try:
            result = _exec_registration_form(
                context, dfs["registration_questions"], dfs.get("registration_options"), is_registration=True
            )
            logs.extend(result)
        except Exception as exc:
            logger.exception("Restore error in registration_form")
            logs.append(f"ERR - registration_form: {exc}")
    if "writing_questions" in dfs:
        try:
            result = _exec_registration_form(
                context, dfs["writing_questions"], dfs.get("writing_options"), is_registration=False
            )
            logs.extend(result)
        except Exception as exc:
            logger.exception("Restore error in character_form")
            logs.append(f"ERR - character_form: {exc}")


def execute_restore(context: dict, zip_bytes: bytes) -> list[str]:
    """Execute the full restore from the ZIP, return all log messages."""
    dfs = _parse_zip(zip_bytes)
    logs: list[str] = []

    if "configuration" in dfs:
        _safe_run(logs, "configuration", _exec_configuration, context, dfs["configuration"])
    if "features" in dfs:
        _safe_run(logs, "features", _exec_features, context, dfs["features"])
    if "tickets" in dfs:
        _safe_run(logs, "tickets", _exec_tickets, context, dfs["tickets"])

    _exec_form_sections(context, dfs, logs)

    if "character_config" in dfs:
        _safe_run(logs, "character_config", _exec_character_config, context, dfs["character_config"])
    if "registration" in dfs:
        _safe_run(logs, "registration", _exec_registration, context, dfs["registration"])

    _exec_writing_types(context, dfs, logs)

    if "questtype" in dfs:
        _safe_run(logs, "questtype", _exec_questtype, context, dfs["questtype"])
    if "abilities" in dfs:
        _safe_run(logs, "abilities", _exec_abilities, context, dfs["abilities"])

    return logs
