from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from django.db.models import Exists, OuterRef

from Admins.models import Ticket
from Users.models import EventWaitlist, WaitlistOffer
from Users.service_pricing import get_unit_price_eth

WAITLIST_PAYMENT_MINUTES = 10


def available_tickets_queryset(event):
    """Unsold tickets not currently reserved by an active waitlist payment window."""
    now = timezone.now()
    active_offer = WaitlistOffer.objects.filter(
        ticket_id=OuterRef("pk"),
        fulfilled_at__isnull=True,
        expired_at__isnull=True,
        expires_at__gte=now,
    )
    return Ticket.objects.filter(event=event, owner_wallet="").exclude(Exists(active_offer))


def expire_stale_waitlist_offers() -> int:
    """Expire offers past deadline; losers lose queue spot; re-offer ticket to next waiter."""
    now = timezone.now()
    expired_ids = list(
        WaitlistOffer.objects.filter(
            fulfilled_at__isnull=True,
            expired_at__isnull=True,
            expires_at__lt=now,
        ).values_list("id", flat=True)
    )
    count = 0
    for oid in expired_ids:
        with transaction.atomic():
            offer = (
                WaitlistOffer.objects.select_for_update()
                .select_related("entry", "ticket", "ticket__event")
                .filter(pk=oid, fulfilled_at__isnull=True, expired_at__isnull=True)
                .first()
            )
            if not offer:
                continue
            ticket = offer.ticket
            entry = offer.entry
            offer.expired_at = now
            offer.save(update_fields=["expired_at"])
            entry.status = EventWaitlist.STATUS_MISSED
            entry.save(update_fields=["status"])
            count += 1
            if ticket.owner_wallet == "":
                offer_ticket_to_waitlist(ticket)
    return count


def offer_ticket_to_waitlist(ticket: Ticket) -> WaitlistOffer | None:
    """
    If ticket has no owner, assign to next waiting user and email payment link.
    Caller should hold appropriate locks or call from a request cycle after refund.
    """
    if ticket.owner_wallet:
        return None
    expire_stale_waitlist_offers()

    entry = (
        EventWaitlist.objects.filter(event=ticket.event, status=EventWaitlist.STATUS_WAITING)
        .select_related("user", "event")
        .order_by("joined_at")
        .first()
    )
    if not entry:
        return None

    unit = get_unit_price_eth(ticket.event)
    token = uuid.uuid4()
    now = timezone.now()
    offer = WaitlistOffer.objects.create(
        entry=entry,
        ticket=ticket,
        token=token,
        unit_price_eth=unit,
        expires_at=now + timedelta(minutes=WAITLIST_PAYMENT_MINUTES),
    )
    entry.status = EventWaitlist.STATUS_OFFERED
    entry.save(update_fields=["status"])

    user = entry.user
    path = f"/Users/waitlist/pay/{token}/"
    try:
        base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
        link = f"{base}{path}" if base else path
    except Exception:
        link = path

    subject = f"Your ticket window — {ticket.event.title}"
    body = (
        f"Hi {user.username},\n\n"
        f"A ticket became available for \"{ticket.event.title}\".\n"
        f"You have {WAITLIST_PAYMENT_MINUTES} minutes to complete payment ({unit:.6f} ETH).\n\n"
        f"Open: {link}\n\n"
        f"If you miss the window, the next person in line will be offered the ticket.\n"
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost"),
            [user.email] if user.email else [],
            fail_silently=True,
        )
    except Exception:
        pass

    return offer
