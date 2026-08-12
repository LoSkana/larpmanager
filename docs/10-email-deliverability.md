# Email Deliverability

How LarpManager keeps its sending reputation healthy: suppression of bad addresses,
ingestion of Amazon SES bounce and complaint events, and one-click unsubscribe.

## Table of Contents

1. [Sending pipeline](#sending-pipeline)
2. [Suppression list](#suppression-list)
3. [SES and SNS setup](#ses-and-sns-setup)
4. [Unsubscribe](#unsubscribe)
5. [Monitoring](#monitoring)

---

## Sending pipeline

`my_send_mail()` queues an `EmailContent` plus one `EmailRecipient` per address, then
`my_send_mail_bkg()` delivers each one through the backend chosen by
`EmailConnectionFactory` (event SMTP, association SMTP, Amazon SES, Django default).

Before delivery a recipient is discarded when it is invalid, on a demo/test domain, or
suppressed. Discarded recipients get a reason in `EmailRecipient.skipped` so they are
not retried forever and remain visible in the admin.

## Suppression list

`EmailSuppression` (in `larpmanager/models/miscellanea.py`) is a global list: an address
that no longer exists is dead for every association, so suppression is not scoped.

| Reason | Effect |
|--------|--------|
| Permanent bounce | blocks immediately |
| Complaint | blocks immediately |
| Manual | blocks immediately |
| Transient bounce | counted, blocks only after `SOFT_BOUNCE_LIMIT` failures |

The helpers live in `larpmanager/mail/suppression.py`:

- `is_suppressed(email)` - cached check used on every send
- `suppress_email(email, reason, raw)` - records an event and activates the block when warranted
- `unsuppress_email(email)` - releases the address, locally and on the SES account list

Suppression blocks **every** message, including transactional ones: the mailbox is
unreachable. Newsletter opt-out is a different thing and only stops bulk sends
(see below).

Staff pages: `/lm/suppressions/` (LarpManager admins) and the Django admin.

## SES and SNS setup

Settings (see `main/settings/prod_example.py`):

```python
AWS_SES_ACCESS_KEY_ID
AWS_SES_SECRET_ACCESS_KEY
AWS_SES_REGION_NAME
AWS_SES_CONFIGURATION_SET   # configuration set tagging outgoing messages
AWS_SNS_TOPIC_ARN           # topic allowed to post notifications
```

AWS side:

1. Create a configuration set (name it as `AWS_SES_CONFIGURATION_SET`).
2. Add an event destination for `Bounce`, `Complaint` and `Reject`, publishing to an SNS topic.
3. Subscribe the topic to `https://larpmanager.com/ses/notification/` over HTTPS. The
   endpoint answers the `SubscriptionConfirmation` automatically.
4. Keep the SES account-level suppression list enabled: it protects the reputation even
   if the webhook is unavailable.
5. Publish DKIM, SPF and DMARC records for every sending domain.

Every payload is signature-verified in `larpmanager/mail/sns.py` before processing:
certificates are only fetched from `*.amazonaws.com`, the topic is checked when pinned,
and notifications are deduplicated on their SNS message id. Without that check anyone
could post forged bounces and blocklist arbitrary users.

## Unsubscribe

Each message carries a signed unsubscribe link (`build_unsubscribe_url()`), scoped to the
association when the mail belongs to one, plus the RFC 8058 headers required by the major
mailbox providers:

```
List-Unsubscribe: <https://.../unsubscribe/<token>/>, <mailto:sender>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

The `unsubscribe` view accepts any POST, so the same url serves both the confirmation
form and the automatic one-click request, which carries no CSRF token.

Unsubscribing sets `Membership.newsletter` to `NO` (association scope) or the
`LarpManagerNewsletter` status to `UNSUBSCRIBED` (platform scope). Both are honoured by
`send_mail_exec()`, the bulk sender; single transactional emails keep flowing.

## Monitoring

`manage.py automate` calls `check_email_reputation()` daily: it reads SES send
statistics of the last 24 hours and notifies admins above 5% bounces or 0.1%
complaints, the thresholds at which AWS places an account under review.
