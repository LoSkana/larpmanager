from typing import Optional
from django.db import models
from django.utils import timezone


class OrganizerNotificationQueue(models.Model):
    """Queue for batching organizer notifications into daily summaries"""

    class NotificationType(models.TextChoices):
        REGISTRATION_NEW = "registration_new", "New Registration"
        REGISTRATION_UPDATE = "registration_update", "Updated Registration"
        REGISTRATION_CANCEL = "registration_cancel", "Cancelled Registration"
        PAYMENT_MONEY = "payment_money", "Money Payment"
        PAYMENT_CREDIT = "payment_credit", "Credit Payment"
        PAYMENT_TOKEN = "payment_token", "Token Payment"
        INVOICE_APPROVAL = "invoice_approval", "Invoice Awaiting Approval"

    event = models.ForeignKey("Event", on_delete=models.CASCADE)
    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices
    )
    registration = models.ForeignKey(
        "Registration", null=True, blank=True, on_delete=models.CASCADE
    )
    payment = models.ForeignKey(
        "AccountingItemPayment", null=True, blank=True, on_delete=models.CASCADE
    )
    invoice = models.ForeignKey(
        "AccountingItem", null=True, blank=True, on_delete=models.CASCADE
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Organizer Notification Queue"
        verbose_name_plural = "Organizer Notification Queue"

    def __str__(self) -> str:
        return f"{self.event.title} - {self.get_notification_type_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


def should_queue_notification(event) -> bool:
    """
    Check if this event uses digest mode for organizer notifications.

    Args:
        event: Event instance

    Returns:
        bool: True if digest mode is enabled, False for immediate emails
    """
    from larpmanager.cache.config import get_event_config

    return get_event_config(event.pk, "mail_orga_digest", False)


def queue_organizer_notification(
    event,
    notification_type: str,
    registration=None,
    payment=None,
    invoice=None,
    details: Optional[dict] = None,
) -> OrganizerNotificationQueue:
    """
    Add notification to queue instead of sending immediately.

    Args:
        event: Event instance
        notification_type: Type of notification (use NotificationType enum values)
        registration: Optional Registration instance
        payment: Optional AccountingItemPayment instance
        invoice: Optional AccountingItem instance
        details: Optional dict with additional context

    Returns:
        OrganizerNotificationQueue: Created notification instance
    """
    return OrganizerNotificationQueue.objects.create(
        event=event,
        notification_type=notification_type,
        registration=registration,
        payment=payment,
        invoice=invoice,
        details=details or {},
    )
