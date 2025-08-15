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

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.accounting.registration import get_date_surcharge
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.base import BaseRegistrationForm, MyForm
from larpmanager.forms.utils import (
    AllowedS2WidgetMulti,
    AssocMemberS2Widget,
    DatePickerInput,
    FactionS2WidgetMulti,
    TicketS2WidgetMulti,
)
from larpmanager.models.casting import Trait
from larpmanager.models.form import QuestionStatus, QuestionType, RegistrationOption, RegistrationQuestion
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character, Faction
from larpmanager.utils.common import get_time_diff_today
from larpmanager.utils.registration import get_reduced_available_count


class RegistrationForm(BaseRegistrationForm):
    class Meta:
        model = Registration
        fields = ("modified",)
        widgets = {"modified": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        run = self.params["run"]
        event = run.event
        self.event = event

        self.profiles = {}
        self.section_descriptions = {}

        self.ticket = None

        self.init_quotas(event, run)

        reg_counts = get_reg_counts(run)

        self.init_ticket(event, reg_counts, run)

        self.waiting_check = (
            self.instance
            and self.instance.ticket
            and self.instance.ticket.tier == TicketTier.WAITING
            or not self.instance
            and "waiting" in run.status
        )

        self.init_additionals()

        self.init_pay_what(run)

        self.init_surcharge(event, run)

        self.init_questions(event, reg_counts)

        self.init_bring_friend()

    def sel_ticket_map(self, ticket):
        """
        Check if given the selected ticket, we need to not require questions reserved
        to other tickets.
        """

        if "reg_que_tickets" not in self.params["features"]:
            return

        for question in self.questions:
            k = "q" + str(question.id)
            if k not in self.fields:
                continue
            tm = [i for i in question.tickets_map if i is not None]
            if ticket not in tm:
                self.fields[k].required = False

    def init_additionals(self):
        if "additional_tickets" not in self.params["features"]:
            return

        self.fields["additionals"] = forms.ChoiceField(
            required=False,
            choices=[(1, "1"), (2, "2"), (3, "3")],
            label=_("Additional tickets"),
            help_text=_("Set if you want to reserve tickets in addition to your"),
        )
        if self.instance:
            self.initial["additionals"] = self.instance.additionals

    def init_bring_friend(self):
        if "bring_friend" not in self.params["features"]:
            return

        if self.instance.pk and self.initial["modified"] > 0:
            return

        mes = _(
            "Enter the “bring a friend” code provided by a registered participant "
            "to receive a %(amount)d discount on your registration fee"
        )
        self.fields["bring_friend"] = forms.CharField(
            required=False,
            max_length=100,
            label=_("Code 'Bring a friend'"),
            help_text=mes % {"amount": self.params.get("bring_friend_discount_from", 0)},
        )

    def init_questions(self, event, reg_counts):
        self.tickets_map = {}
        if self.waiting_check:
            self.questions = []
            return
        self._init_reg_question(self.instance, event)
        for q in self.questions:
            self.init_question(q, reg_counts)
        self.tickets_map = json.dumps(self.tickets_map)

    def init_question(self, q, reg_counts):
        if q.skip(self.instance, self.params["features"]):
            return

        k = self._init_field(q, reg_counts, orga=False)

        if q.profile:
            self.profiles["id_" + k] = q.profile_thumb.url

        if q.section:
            self.sections["id_" + k] = q.section.name
            if q.section.description:
                self.section_descriptions[q.section.name] = q.section.description

        if "reg_que_tickets" in self.params["features"]:
            tm = [i for i in q.tickets_map if i is not None]
            if tm:
                self.tickets_map[k] = tm

    def init_surcharge(self, event, run):
        # date surcharge
        surcharge = get_date_surcharge(self.instance, event)
        if surcharge == 0:
            return
        ch = [(0, f"{surcharge}{self.params['currency_symbol']}")]
        self.fields["character"] = forms.ChoiceField(
            required=True,
            choices=ch,
            label=_("Surcharge"),
            help_text=_("Registration surcharge"),
        )

    def init_pay_what(self, run):
        if "pay_what_you_want" not in self.params["features"]:
            return

        if "waiting" in run.status:
            return

        lbl = run.event.get_config("pay_what_you_want_label", _("Free donation"))
        help_text = run.event.get_config("pay_what_you_want_descr", _("Freely indicate the amount of your donation"))
        self.fields["pay_what"] = forms.IntegerField(
            min_value=0, max_value=1000, label=lbl, help_text=help_text, required=False
        )
        if self.instance.pk and self.instance.pay_what:
            self.initial["pay_what"] = int(self.instance.pay_what)
        else:
            self.initial["pay_what"] = 0

    def init_quotas(self, event, run):
        quota_chs = []
        if "reg_quotas" in self.params["features"] and "waiting" not in run.status:
            qt_label = [
                _("Single payment"),
                _("Two quotas"),
                _("Three quotas"),
                _("Four quotas"),
                _("Five quotas"),
            ]
            dff = get_time_diff_today(run.end)
            for el in RegistrationQuota.objects.filter(event=event).order_by("quotas"):
                if dff > el.days_available or (self.instance and el.quotas == self.instance.quotas):
                    label = qt_label[int(el.quotas) - 1]
                    if el.surcharge > 0:
                        label += f" ({el.surcharge}€)"
                    quota_chs.append((el.quotas, label))
        if not quota_chs:
            quota_chs.append((1, _("Default")))
        ht = _("The number of payments to split the fee")
        ht += " " + _("The ticket will be divided equally in the number of quotas indicated") + "."
        ht += " " + _("Payment deadlines will be similarly equally divided, based on the date of registration") + "."
        self.fields["quotas"] = forms.ChoiceField(required=True, choices=quota_chs, label=_("Quotas"), help_text=ht)
        if len(quota_chs) == 1:
            self.fields["quotas"].widget = forms.HiddenInput()
            self.initial["quotas"] = quota_chs[0][0]
        if self.instance.pk and self.instance.quotas:
            self.initial["quotas"] = self.instance.quotas
            # print(self.initial['quotas'])
            # print(self.instance.quotas)

    def init_ticket(self, event, reg_counts, run):
        # check registration tickets options
        tickets = self.get_available_tickets(event, reg_counts, run)

        # get ticket names / description
        ticket_choices = []
        ticket_help = _("Your registration ticket")
        for r in tickets:
            name = r.get_form_text(run, cs=self.params["currency_symbol"])
            ticket_choices.append((r.id, name))
            if r.description:
                ticket_help += f"<p><b>{r.name}</b>: {r.description}</p>"

        self.fields["ticket"] = forms.ChoiceField(
            required=True, choices=ticket_choices, label=_("Ticket"), help_text=ticket_help
        )
        # ~ if len(tickets) == 1:
        # ~ self.fields['ticket'].widget = forms.HiddenInput()
        # ~ self.initial['ticket'] = tickets[0].id
        # ~ self.ticket_price = tickets[0].price
        # to remove
        if self.instance and self.instance.ticket:
            self.initial["ticket"] = self.instance.ticket.id
        elif "ticket" in self.params and self.params["ticket"]:
            self.initial["ticket"] = self.params["ticket"]
            # print(self.initial['ticket'])

    def has_ticket(self, tier):
        return self.instance.pk and self.instance.ticket and self.instance.ticket.tier == tier

    def has_ticket_primary(self):
        not_primary_tiers = [TicketTier.WAITING, TicketTier.FILLER]
        return self.instance.pk and self.instance.ticket and self.instance.ticket.tier not in not_primary_tiers

    def check_ticket_visibility(self, ticket):
        if ticket.visible:
            return True

        if "ticket" in self.params and self.params["ticket"] == ticket.id:
            return True

        if self.instance.pk and self.instance.ticket == ticket:
            return True

        return False

    def get_available_tickets(self, event, reg_counts, run):
        for tier in [TicketTier.STAFF, TicketTier.NPC]:
            # If the user is registered as a staff, show those options
            if self.has_ticket(tier):
                return RegistrationTicket.objects.filter(event=event, tier=tier).order_by("order")

        # Check closed inscriptions
        if not self.instance.pk and "closed" in run.status:
            return []

        # See players options
        tickets = []
        que_tickets = RegistrationTicket.objects.filter(event=event).order_by("order")
        if self.gift:
            que_tickets = que_tickets.filter(giftable=True)

        for ticket in que_tickets:
            if not self.check_ticket_visibility(ticket):
                continue

            if self.skip_ticket_type(event, run, ticket):
                continue

            if self.skip_ticket_max(reg_counts, ticket):
                continue

            if self.skip_ticket_reduced(run, ticket):
                continue

            tickets.append(ticket)

        return tickets

    def skip_ticket_reduced(self, run, ticket):
        # if this reduced, check count
        if ticket.tier == TicketTier.REDUCED:
            if not self.instance or ticket != self.instance.ticket:
                ticket.available = get_reduced_available_count(run)
                if ticket.available <= 0:
                    return True
        return False

    def skip_ticket_max(self, reg_counts, ticket):
        # If the option has a maximum roof, check has not been reached
        if ticket.max_available > 0:
            if not self.instance or ticket != self.instance.ticket:
                ticket.available = ticket.max_available
                key = f"tk_{ticket.id}"
                if key in reg_counts:
                    ticket.available -= reg_counts[key]
                if ticket.available <= 0:
                    return True
        return False

    def skip_ticket_type(self, event, run, ticket):
        if "ticket" in self.params:
            return False

        # Show Waiting tickets only if you are Waiting, or if the player is enrolled in Waiting
        if ticket.tier == TicketTier.WAITING:
            if "waiting" not in run.status and not self.has_ticket(TicketTier.WAITING):
                return True

        elif ticket.tier == TicketTier.FILLER:
            filler_alway = event.get_config("filler_alway", False)
            if filler_alway:
                # Show Filler Tickets only if you have been filler or primary, or if the player is signed up for Filler
                if (
                    "filler" not in run.status
                    and "primary" not in run.status
                    and not self.has_ticket(TicketTier.FILLER)
                ):
                    return True
            # Show Filler Tickets only if you have been fillers, or if the player is subscribed Filler
            elif "filler" not in run.status and not self.has_ticket(TicketTier.FILLER):
                return True

        # Show Primary Tickets only if he was primary, or if the player is registered
        elif "primary" not in run.status and not self.has_ticket_primary():
            return True

        return False

    def clean(self):
        form_data = super().clean()
        run = self.params["run"]

        if "bring_friend" in self.params["features"] and "bring_friend" in form_data:
            cod = form_data["bring_friend"]
            if cod:
                try:
                    Registration.objects.get(special_cod=cod, run__event=run.event)
                except Exception:
                    self.add_error("bring_friend", "I'm sorry, this friend code was not found")

        return form_data


class RegistrationGiftForm(RegistrationForm):
    gift = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        keep = ["run", "ticket"]
        for q in self.questions:
            if q.giftable:
                keep.append("q" + str(q.id))
        list_del = [s for s in self.fields if s not in keep]
        for field in list_del:
            del self.fields[field]
            key = f"id_{field}"
            if key in self.mandatory:
                self.mandatory.remove(key)

        self.has_mandatory = len(self.mandatory) > 0


class OrgaRegistrationForm(BaseRegistrationForm):
    page_info = _("This page allows you to add or edit a signup to this event")

    page_title = _("Registrations")

    load_templates = ["share"]

    load_js = ["characters-reg-choices"]

    class Meta:
        model = Registration

        exclude = (
            "search",
            "modified",
            "refunded",
            "cancellation_date",
            "surcharge",
            "characters",
            "num_payments",
            "alert",
            "deadline",
            "redeem_code",
            "tot_payed",
            "tot_iscr",
            "quota",
        )

        widgets = {"member": AssocMemberS2Widget}

    def get_automatic_field(self):
        s = super().get_automatic_field()
        # I decide in the init code whether to remove run field or not
        s.remove("run")
        return s

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.run = self.params["run"]
        self.event = self.params["run"].event

        self.fields["member"].widget.set_assoc(self.params["a_id"])

        self.allow_run_choice()

        reg_section = _("Registration")
        char_section = _("Character")
        add_section = _("Details")
        main_section = _("Main")

        self.sections["id_member"] = reg_section
        self.sections["id_run"] = reg_section

        self.init_quotas(reg_section)

        self.init_ticket(reg_section)

        self.init_additionals(reg_section)

        self.init_pay_what(reg_section)

        # ## CHARACTERS
        if "character" in self.params["features"]:
            self.init_character(char_section)

        # ## REGISTRATION OPTIONS
        self.init_orga_fields(main_section)

        if "unique_code" in self.params["features"]:
            self.sections["id_special_cod"] = add_section
            self.reorder_field("special_cod")
        else:
            self.delete_field("special_cod")

        if "reg_que_sections" not in self.params["features"]:
            self.show_sections = True

    def init_additionals(self, reg_section):
        if "additional_tickets" in self.params["features"]:
            self.sections["id_additionals"] = reg_section
        else:
            self.delete_field("additionals")

    def init_pay_what(self, reg_section):
        if "pay_what_you_want" in self.params["features"]:
            self.sections["id_pay_what"] = reg_section
            self.fields["pay_what"].label = self.params["run"].event.get_config(
                "pay_what_you_want_label", _("Free donation")
            )
            self.fields["pay_what"].help_text = self.params["run"].event.get_config(
                "pay_what_you_want_descr", _("Freely indicate the amount of your donation")
            )
        else:
            self.delete_field("pay_what")

    def init_ticket(self, reg_section):
        tickets = [
            (m.id, m.get_form_text(cs=self.params["currency_symbol"]))
            for m in RegistrationTicket.objects.filter(event=self.params["run"].event).order_by("-price")
        ]
        self.fields["ticket"].choices = tickets
        if len(tickets) == 1:
            self.fields["ticket"].widget = forms.HiddenInput()
            self.initial["ticket"] = tickets[0][0]
        self.sections["id_ticket"] = reg_section

    def init_quotas(self, reg_section):
        if "reg_quotas" not in self.params["features"]:
            self.delete_field("quotas")
            return

        quota_chs = [(1, "Pagamento unico"), (2, "Due quote"), (3, "Tre quote")]
        self.fields["quotas"] = forms.ChoiceField(
            required=True,
            choices=quota_chs,
            label=_("Quotas"),
            help_text=_("The number of payments to split the fee"),
        )
        self.initial["quotas"] = self.instance.quotas
        self.sections["id_quotas"] = reg_section

    def init_character(self, char_section):
        # CHARACTER AND QUESTS
        if "orga_characters" not in self.params or not self.params["orga_characters"]:
            return

        mine = set()
        if self.instance.pk:
            self.initial["characters_new"] = self.get_init_multi_character()
            mine.update([el for el in self.initial["characters_new"]])
        taken_characters = set(
            RegistrationCharacterRel.objects.filter(reg__run_id=self.params["run"].id).values_list(
                "character_id", flat=True
            )
        )
        taken_characters = taken_characters - mine
        self.fields["characters_new"] = forms.ModelMultipleChoiceField(
            label=_("Characters"),
            queryset=self.params["run"].event.get_elements(Character).exclude(pk__in=taken_characters),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains", "number__icontains"]),
            required=False,
        )
        self.sections["id_characters_new"] = char_section

        if "questbuilder" in self.params["features"]:
            already = []
            assigned = []
            char = None
            char_ids = self.get_init_multi_character()
            if char_ids:
                char = Character.objects.get(pk=char_ids[0])
            for tnum, trait in self.params["traits"].items():
                if char and char.number == trait["char"]:
                    assigned.append(tnum)
                    continue
                already.append(tnum)
            available = Trait.objects.filter(event=self.event).exclude(number__in=already)
            for qtnum, qt in self.params["quest_types"].items():
                qt_id = f"qt_{qt['number']}"
                key = "id_" + qt_id
                self.sections[key] = char_section
                choices = [("0", _("--- NOT ASSIGNED ---"))]
                for _qnum, q in self.params["quests"].items():
                    if q["typ"] != qtnum:
                        continue
                    for t in available:
                        if t.quest_id != q["id"]:
                            continue
                        choices.append((t.id, f"Q{q['number']} {q['name']} - {t}"))
                        if t.number in assigned:
                            self.initial[qt_id] = t.id

                self.fields[qt_id] = forms.ChoiceField(required=True, choices=choices, label=qt["name"])

    def clean_member(self):
        data = self.cleaned_data["member"]

        if "request" in self.params:
            post = self.params["request"].POST
            if "delete" in post and post["delete"] == "1":
                return data

        for reg in Registration.objects.filter(
            member=data,
            run=self.params["run"],
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
        ):
            if reg.pk != self.instance.pk:
                raise ValidationError("User already has a registration for this event!")

        return data

    def get_init_multi_character(self):
        que = RegistrationCharacterRel.objects.filter(reg__id=self.instance.pk)
        return que.values_list("character_id", flat=True)

    def _save_multi(self, s, instance):
        if s != "characters_new":
            return super()._save_multi(s, instance)

        old = set(self.get_init_multi_character())
        new = set(self.cleaned_data["characters_new"].values_list("pk", flat=True))

        for ch in old - new:
            RegistrationCharacterRel.objects.filter(character_id=ch, reg_id=instance.pk).delete()
        for ch in new - old:
            RegistrationCharacterRel.objects.create(character_id=ch, reg_id=instance.pk)

    def clean_characters_new(self):
        data = self.cleaned_data["characters_new"]

        for ch in data.values_list("pk", flat=True):
            qs = RegistrationCharacterRel.objects.filter(
                character_id=ch,
                reg__run=self.params["run"],
                reg__cancellation_date__isnull=True,
            )
            if self.instance.pk:
                qs = qs.exclude(reg__id=self.instance.pk)
            if len(qs) > 0:
                el = qs.first()
                raise ValidationError(
                    f"Character '{el.character}' already assigned to the player '{el.reg.member}' for this event!"
                )

        return data


class RegistrationCharacterRelForm(MyForm):
    class Meta:
        model = RegistrationCharacterRel
        exclude = ("reg", "character")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        dl = ["profile"]

        for s in ["name", "pronoun", "song", "public", "private"]:
            if not self.params["event"].get_config("custom_character_" + s, False):
                dl.append(s)

        if "custom_name" not in self.initial or not self.initial["custom_name"]:
            self.initial["custom_name"] = self.instance.character.name

        for m in dl:
            self.delete_field("custom_" + m)


class OrgaRegistrationTicketForm(MyForm):
    page_info = _("This page allows you to add or change the types of ticket with which participants can register")

    page_title = _("Tickets")

    class Meta:
        model = RegistrationTicket
        fields = "__all__"
        exclude = ("number", "order")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tiers = self.get_tier_available(self.params["run"].event)
        if len(tiers) > 1:
            self.fields["tier"].choices = tiers
        else:
            del self.fields["tier"]

        if "casting" not in self.params["features"]:
            self.delete_field("casting_priority")

        if "gift" not in self.params["features"]:
            self.delete_field("giftable")

    @staticmethod
    def get_tier_available(event):
        aux = []
        ticket_features = {
            TicketTier.LOTTERY: "lottery",
            TicketTier.WAITING: "waiting",
            TicketTier.FILLER: "filler",
            TicketTier.PATRON: "reduced",
            TicketTier.REDUCED: "reduced",
        }
        ticket_configs = {
            TicketTier.STAFF: "staff",
            TicketTier.NPC: "npc",
            TicketTier.COLLABORATOR: "collaborator",
            TicketTier.SELLER: "seller",
        }
        ev_features = get_event_features(event.id)
        for tp in TicketTier.choices:
            (value, label) = tp
            # skip ticket if feature not set
            if value in ticket_features:
                if ticket_features[value] not in ev_features:
                    continue

            # skip ticket if config not set
            if value in ticket_configs:
                if not event.get_config(f"ticket_{ticket_configs[value]}", False):
                    continue

            aux.append(tp)
        return aux


class OrgaRegistrationSectionForm(MyForm):
    page_info = _("This page allows you to add or edit sections in the signup form")

    page_title = _("Form section")

    class Meta:
        model = RegistrationSection
        exclude = ["order"]


class OrgaRegistrationQuestionForm(MyForm):
    page_info = _("This page allows you to add or edit a question from the sign up form")

    page_title = _("Form element")

    class Meta:
        model = RegistrationQuestion
        exclude = ["order"]

        widgets = {
            "factions": FactionS2WidgetMulti,
            "tickets": TicketS2WidgetMulti,
            "allowed": AllowedS2WidgetMulti,
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["factions"].widget.set_event(self.params["event"])

        self.fields["typ"].choices = [choice for choice in QuestionType.choices if len(choice[0]) == 1]

        if "reg_que_sections" not in self.params["features"]:
            self.delete_field("section")
        else:
            ch = [(m.id, str(m)) for m in RegistrationSection.objects.filter(event=self.params["run"].event)]
            ch.insert(0, ("", _("--- Empty")))
            self.fields["section"].choices = ch

        if "reg_que_allowed" not in self.params["features"]:
            self.delete_field("allowed")
        else:
            self.fields["allowed"].widget.set_event(self.params["event"])

        if "reg_que_tickets" not in self.params["features"]:
            self.delete_field("tickets")
        else:
            self.fields["tickets"].widget.set_event(self.params["event"])

        if "reg_que_faction" not in self.params["features"]:
            self.delete_field("factions")
        else:
            self.fields["factions"].choices = [
                (m.id, str(m)) for m in self.params["run"].event.get_elements(Faction).order_by("number")
            ]

        if "gift" not in self.params["features"]:
            self.delete_field("giftable")

        # Set status help
        visible_choices = {v for v, _ in self.fields["status"].choices}

        help_texts = {
            QuestionStatus.OPTIONAL: "The question is shown, and can be filled by the player",
            QuestionStatus.MANDATORY: "The question needs to be filled by the player",
            QuestionStatus.DISABLED: "The question is shown, but cannot be changed by the player",
            QuestionStatus.HIDDEN: "The question is not shown to the player",
        }

        self.fields["status"].help_text = ", ".join(
            f"<b>{choice.label}</b>: {text}" for choice, text in help_texts.items() if choice.value in visible_choices
        )


class OrgaRegistrationOptionForm(MyForm):
    page_info = _("This page allows you to add or edit an option in a sign up form question")

    page_title = _("Form Options")

    class Meta:
        model = RegistrationOption
        exclude = ["order"]
        widgets = {"question": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "question_id" in self.params:
            self.initial["question"] = self.params["question_id"]


class OrgaRegistrationQuotaForm(MyForm):
    page_info = _(
        "This page allows you to add or modify the dynamic instalments with which the participant can split the payment"
    )

    page_title = _("Dynamic rates")

    class Meta:
        model = RegistrationQuota
        exclude = ("number",)


class OrgaRegistrationInstallmentForm(MyForm):
    page_info = _("This page allows you to add or change the fixed instalments in which a participant must pay")

    page_title = _("Fixed instalments")

    class Meta:
        model = RegistrationInstallment
        exclude = ("number",)

        widgets = {
            "date_deadline": DatePickerInput,
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tickets"].widget.set_event(self.params["event"])

    def clean(self):
        cleaned_data = super().clean()

        date_deadline = cleaned_data.get("date_deadline")
        days_deadline = cleaned_data.get("days_deadline")
        if days_deadline and date_deadline:
            self.add_error(
                "days_deadline",
                "Choose only one deadline for this installment, either by date or number of days!",
            )

        return cleaned_data


class OrgaRegistrationSurchargeForm(MyForm):
    page_info = _("This page allows you to add or edit the registration surcharges")

    page_title = _("Surcharge")

    class Meta:
        model = RegistrationSurcharge
        exclude = ("number",)

        widgets = {"date": DatePickerInput}


class PreRegistrationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.ctx = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)

        self.pre_reg = 1 + len(self.ctx["already"])

        cho = [("", "----")] + [(c.id, c.name) for c in self.ctx["choices"]]
        self.fields["new_event"] = forms.ChoiceField(
            required=False, choices=cho, label=_("Event"), help_text=_("Select the event you wish to pre-register for")
        )

        existing = [al.pref for al in self.ctx["already"]]
        max_existing = max(existing) if existing else 1
        prefs = [r for r in range(1, max_existing + 4) if r not in existing]
        cho_pref = [(r, r) for r in prefs]
        self.fields["new_pref"] = forms.ChoiceField(
            required=False,
            choices=cho_pref,
            label=_("Preference"),
            help_text=_("Enter the order of preference of your pre-registration (1 is the maximum)"),
        )
        self.initial["new_pref"] = min(prefs)

        self.fields["new_info"] = forms.CharField(
            required=False,
            max_length=255,
            label=_("Informations"),
            help_text=_("Is there anything else you would like to tell us") + "?",
        )
