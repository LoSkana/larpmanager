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

from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _

from larpmanager.models.association import Association
from larpmanager.models.base import BaseModel, PaymentMethod
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.utils import UploadToPathAndRename, download, generate_id, my_uuid_short


class PaymentType(models.TextChoices):
    REGISTRATION = "r", "registration"
    MEMBERSHIP = "m", "membership"
    DONATE = "d", "donation"
    COLLECTION = "g", "collection"


class PaymentStatus(models.TextChoices):
    CREATED = "r", "Created"
    SUBMITTED = "s", "Submitted"
    CONFIRMED = "c", "Confirmed"
    CHECKED = "k", "Checked"


class PaymentInvoice(BaseModel):
    search = models.CharField(max_length=500, editable=False)

    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    typ = models.CharField(max_length=1, choices=PaymentType.choices)

    invoice = models.FileField(
        upload_to=UploadToPathAndRename("wire/"),
        null=True,
        blank=True,
        verbose_name=_("Statement"),
        help_text=_("Statement issued by the bank as proof of the issuance of the transfer (as pdf file)"),
    )

    text = models.TextField(null=True, blank=True)

    status = models.CharField(max_length=1, choices=PaymentStatus.choices, default=PaymentStatus.CREATED, db_index=True)

    method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)

    mc_gross = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name=_("Gross"),
        help_text=_("Total payment sent"),
    )

    mc_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Transactions"),
        help_text=_("Withheld as transaction fee"),
    )

    idx = models.IntegerField(default=0)

    txn_id = models.CharField(max_length=50, null=True, blank=True)

    causal = models.CharField(max_length=200)

    cod = models.CharField(max_length=50, unique=True, db_index=True)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    reg = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True,
        blank=True,
    )

    verified = models.BooleanField(default=False)

    hide = models.BooleanField(default=False)

    key = models.CharField(max_length=500, null=True)

    class Meta:
        indexes = [models.Index(fields=["key", "status"]), models.Index(fields=["assoc", "cod"])]

    def __str__(self):
        return (
            f"({self.status}) Invoice for {self.member} - {self.causal} - {self.txn_id} {self.mc_gross} {self.mc_fee}"
        )

    def download(self):
        if not self.invoice:
            return ""
        if not self.invoice.name:
            return ""
        # noinspection PyUnresolvedReferences
        return download(self.invoice.url)

    def get_details(self):
        s = ""
        if not self.method:
            return s
        # slug = self.method.slug
        if self.invoice:
            s += f" <a href='{self.download()}'>Download</a>"
        if self.text:
            s += f" {self.text}"
        if self.cod:
            s += f" {self.cod}"
        return s


class ElectronicInvoice(BaseModel):
    inv = models.OneToOneField(
        PaymentInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="electronicinvoice"
    )

    progressive = models.IntegerField()

    number = models.IntegerField()

    year = models.IntegerField()

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    xml = models.TextField(blank=True, null=True)

    response = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["number", "year", "assoc", "deleted"],
                name="unique_number_with_optional",
            ),
            UniqueConstraint(
                fields=["number", "year", "assoc"],
                condition=Q(deleted=None),
                name="unique_number_without_optional",
            ),
            UniqueConstraint(
                fields=["progressive", "deleted"],
                name="unique_progressive_with_optional",
            ),
            UniqueConstraint(
                fields=["progressive"],
                condition=Q(deleted=None),
                name="unique_progressive_without_optional",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.progressive:
            highest_progressive = ElectronicInvoice.objects.aggregate(models.Max("progressive"))["progressive__max"]
            self.progressive = highest_progressive + 1 if highest_progressive else 1

        if not self.number:
            que = ElectronicInvoice.objects.filter(year=self.year, assoc=self.assoc)
            highest_number = que.aggregate(models.Max("number"))["number__max"]
            self.number = highest_number + 1 if highest_number else 1

        super().save(*args, **kwargs)


class AccountingItem(BaseModel):
    SCENOGR = "a"
    COST = "b"
    PROP = "c"
    ELECTR = "d"
    PROMOZ = "e"
    TRANS = "f"
    KITCH = "g"
    LOCAT = "h"
    SEGRET = "i"
    OTHER = "j"
    EXPENSE_CHOICES = [
        (SCENOGR, _("Set design - staging, materials")),
        (COST, _("Costumes - make up, cloth, armor")),
        (PROP, _("Prop - weapons, props")),
        (ELECTR, _("Electronics - computers, hitech, lights")),
        (PROMOZ, _("Promotion - site, advertising")),
        (TRANS, _("Transportation - gas, highway")),
        (KITCH, _("Kitchen - food, tableware")),
        (LOCAT, _("Location - rent, gas, overnight stays")),
        (SEGRET, _("Secretarial - stationery, printing")),
        (OTHER, _("Other")),
    ]

    MATER = "1"
    SERV = "2"
    GODIM = "3"
    PERSON = "4"
    DIVER = "5"
    BALANCE_CHOICES = [
        (MATER, _("Raw materials, auxiliaries, consumables and goods")),
        (SERV, _("Services")),
        (GODIM, _("Use of third party assets")),
        (PERSON, _("Personal")),
        (DIVER, _("Miscellaneous operating expenses")),
    ]

    search = models.CharField(max_length=150, editable=False)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, null=True, blank=True)

    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    inv = models.OneToOneField(PaymentInvoice, on_delete=models.SET_NULL, null=True, blank=True)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    hide = models.BooleanField(default=False)

    def __str__(self):
        s = "Voce contabile"
        # noinspection PyUnresolvedReferences
        if self.id:
            # noinspection PyUnresolvedReferences
            s += f" &{self.id}"
        s += f" - {self.__class__.__name__}"
        if self.member:
            s += f" - {self.member}"
        return s

    class Meta:
        abstract = True

    def short_descr(self):
        if not hasattr(self, "descr"):
            return ""
        # noinspection PyUnresolvedReferences
        return self.descr[:100]


class AccountingItemTransaction(AccountingItem):
    reg = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="accounting_items_t", null=True, blank=True
    )

    user_burden = models.BooleanField(default=False)


class AccountingItemMembership(AccountingItem):
    year = models.IntegerField()

    class Meta:
        indexes = [models.Index(fields=["assoc", "year"])]


class AccountingItemDonation(AccountingItem):
    descr = models.CharField(max_length=1000)


class AccountingItemOther(AccountingItem):
    CREDIT = "c"  # credits gained
    TOKEN = "t"  # token gained
    REFUND = "r"  # refund given
    OTHER_CHOICES = [(CREDIT, _("Credits")), (TOKEN, _("Tokens")), (REFUND, _("Refund"))]

    oth = models.CharField(max_length=1, choices=OTHER_CHOICES)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, null=True, blank=True)

    descr = models.CharField(max_length=150)

    cancellation = models.BooleanField(default=False)

    ref_addit = models.IntegerField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["run", "oth"])]

    def __str__(self):
        s = _("Credit assignment")
        if self.oth == AccountingItemOther.TOKEN:
            s = _("Tokens assignment")
        elif self.oth == AccountingItemOther.REFUND:
            s = _("Refund")
        if self.member:
            s += f" - {self.member}"
        return s


class AccountingItemPayment(AccountingItem):
    MONEY = "a"
    CREDIT = "b"
    TOKEN = "c"
    PAYMENT_CHOICES = [(MONEY, "Money"), (CREDIT, "Credit"), (TOKEN, "Token")]

    pay = models.CharField(max_length=1, choices=PAYMENT_CHOICES, default=MONEY)

    reg = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="accounting_items_p", null=True, blank=True
    )

    info = models.CharField(max_length=150, null=True, blank=True)

    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        indexes = [models.Index(fields=["pay", "reg"])]


class AccountingItemExpense(AccountingItem):
    invoice = models.FileField(upload_to=UploadToPathAndRename("invoice/"))

    run = models.ForeignKey(Run, on_delete=models.CASCADE, null=True, blank=True)

    descr = models.CharField(max_length=150)

    exp = models.CharField(
        max_length=1,
        choices=AccountingItem.EXPENSE_CHOICES,
        verbose_name=_("Type"),
        help_text=_("Indicate the outflow category"),
    )

    balance = models.CharField(
        max_length=1,
        choices=AccountingItem.BALANCE_CHOICES,
        verbose_name=_("Balance"),
        help_text=_("Indicate how spending is allocated at the budget level"),
        null=True,
        blank=False,
    )

    is_approved = models.BooleanField(default=False)

    def download(self):
        # noinspection PyUnresolvedReferences
        return download(self.invoice.url)


class AccountingItemFlow(AccountingItem):
    class Meta:
        abstract = True

    run = models.ForeignKey(Run, on_delete=models.CASCADE, null=True, blank=True)

    descr = models.CharField(max_length=500, verbose_name=_("Description"))

    invoice = models.FileField(upload_to=UploadToPathAndRename("invoice_outflow/"), null=True, blank=True)

    payment_date = models.DateField(
        null=True,
        verbose_name=_("Payment date"),
        help_text=_("Indicate the exact date in which the payment has been performed"),
    )

    def download(self):
        if not self.invoice:
            return ""
        # noinspection PyUnresolvedReferences
        return download(self.invoice.url)


class AccountingItemOutflow(AccountingItemFlow):
    exp = models.CharField(
        max_length=1,
        choices=AccountingItem.EXPENSE_CHOICES,
        verbose_name=_("Type"),
        help_text=_("Indicate the outflow category"),
    )

    balance = models.CharField(
        max_length=1,
        choices=AccountingItem.BALANCE_CHOICES,
        verbose_name=_("Balance"),
        help_text=_("Indicate how spending is allocated at the budget level"),
        null=True,
        blank=False,
    )


class AccountingItemInflow(AccountingItemFlow):
    pass


class Discount(BaseModel):
    STANDARD = "a"
    FRIEND = "f"
    INFLUENCER = "I"
    PLAYAGAIN = "p"
    GIFT = "g"
    TYPE_CHOICES = [
        (STANDARD, _("Standard")),
        (PLAYAGAIN, _("Play Again")),
    ]

    name = models.CharField(max_length=100, help_text=_("Name of the discount - internal use"))

    runs = models.ManyToManyField(
        Run,
        related_name="discounts",
        blank=True,
        help_text=_("Indicate the runs for which the discount is active"),
    )

    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("Indicate the value of the discount, it will be deducted from the total amount calculated"),
    )

    max_redeem = models.IntegerField(
        help_text=_("Indicate the maximum number of such discounts that can be requested (0 for infinite uses)")
    )

    cod = models.CharField(
        max_length=12,
        default=my_uuid_short,
        verbose_name=_("Code"),
        help_text=_(
            "Indicate the special discount code, to be communicated to the participants, which "
            "will need to be entered during registration."
        ),
    )

    typ = models.CharField(
        max_length=1,
        choices=TYPE_CHOICES,
        verbose_name=_("Type"),
        help_text=_(
            "Indicate the type of discount: standard, play again (only available to those who "
            "have already played this event)"
        ),
    )

    visible = models.BooleanField(
        default=False,
        help_text=_("Indicates whether the discount is visible and usable by participants"),
    )

    only_reg = models.BooleanField(
        default=True,
        help_text=_(
            "Indicate whether the discount can be used only on new enrollment, or whether it "
            "can be used by already registered participants."
        ),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="discounts", null=True)

    number = models.IntegerField()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_discount_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_discount_without_optional",
            ),
        ]

    def __str__(self):
        # noinspection PyUnresolvedReferences
        s = f"{self.name} ({self.get_typ_display()}) {self.value}"
        if self.event:
            # noinspection PyUnresolvedReferences
            s += self.event.assoc.get_currency_symbol()
        return s

    def show(self, run=None):
        js = {"value": self.value, "max_redeem": self.max_redeem}
        for s in ["name"]:
            self.upd_js_attr(js, s)
        return js

    def show_event(self):
        # noinspection PyUnresolvedReferences
        return ", ".join([str(c) for c in self.runs.all()])


class AccountingItemDiscount(AccountingItem):
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
    )

    disc = models.ForeignKey(Discount, on_delete=models.CASCADE, related_name="accounting_items")

    expires = models.DateTimeField(null=True, blank=True)

    detail = models.IntegerField(null=True, blank=True)

    def show(self):
        j = {"name": self.disc.name, "value": self.value}
        if self.expires:
            # noinspection PyUnresolvedReferences
            j["expires"] = self.expires.strftime("%H:%M")
        else:
            j["expires"] = ""
        return j


class Collection(BaseModel):
    OPEN = "o"
    DONE = "d"
    PAYED = "p"
    STATUS_CHOICES = [
        (OPEN, _("Open")),
        (DONE, _("Close")),
        (PAYED, _("Delivered")),
    ]

    name = models.CharField(max_length=100, null=True)

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=OPEN)

    contribute_code = models.CharField(max_length=16, null=True, db_index=True)

    redeem_code = models.CharField(max_length=16, null=True, db_index=True)

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="collections_received",
        null=True,
        blank=True,
    )

    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="collections_runs",
        null=True,
        blank=True,
    )

    organizer = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="collections_created")

    total = models.IntegerField(default=0)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __str__(self):
        if self.member:
            return f"Colletta per {self.member}"
        else:
            return f"Colletta per {self.name}"

    def display_member(self):
        if self.member:
            # noinspection PyUnresolvedReferences
            return self.member.display_member()
        return self.name

    def unique_contribute_code(self):
        for _idx in range(5):
            cod = generate_id(16)
            if not Collection.objects.filter(contribute_code=cod).exists():
                self.contribute_code = cod
                return
        raise ValueError("Too many attempts to generate the code")

    def unique_redeem_code(self):
        for _idx in range(5):
            cod = generate_id(16)
            if not Collection.objects.filter(redeem_code=cod).exists():
                self.redeem_code = cod
                return
        raise ValueError("Too many attempts to generate the code")


class AccountingItemCollection(AccountingItem):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="collection_gifts")


class RefundStatus(models.TextChoices):
    REQUEST = "r", _("Request")
    PAYED = "p", _("Delivered")


class RefundRequest(BaseModel):
    search = models.CharField(max_length=200, editable=False)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="refund_requests")

    status = models.CharField(max_length=1, choices=RefundStatus.choices, default=RefundStatus.REQUEST, db_index=True)

    details = models.TextField(
        max_length=2000,
        verbose_name=_("Details"),
        help_text=_(
            "Indicate all references of how you want your refund to be paid  (ex: IBAN and "
            "full bank details, paypal link, etc)"
        ),
    )

    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Refund"),
        help_text=_("Indicates the amount of reimbursement desired"),
    )

    hide = models.BooleanField(default=False)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __str__(self):
        return f"Refund request of {self.member}"

    # ## Workshops


class RecordAccounting(BaseModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="rec_accs", null=True, blank=True)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="rec_accs")

    global_sum = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Global balance"))

    bank_sum = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Overall balance"))
