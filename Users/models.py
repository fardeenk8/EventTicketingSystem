import secrets

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from Admins.models import Event, Ticket


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    wallet = models.CharField(max_length=200, blank=True)
    referral_code = models.CharField(max_length=16, blank=True, default="", db_index=True)
    referred_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_signups",
    )

    def save(self, *args, **kwargs):
        if not self.referral_code:
            for _ in range(64):
                code = secrets.token_hex(4).upper()
                qs = Profile.objects.filter(referral_code=code)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                if not qs.exists():
                    self.referral_code = code
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} Profile"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        Profile.objects.get_or_create(user=instance)
        instance.profile.save()

class TicketPurchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_eth = models.FloatField()
    tx_hash = models.CharField(max_length=200)
    promo_code_used = models.CharField(max_length=64, blank=True, default="")
    discount_percent_applied = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.event.title} ({self.quantity})"


class PromoCode(models.Model):
    """Time-bound discount code (optionally scoped to one event)."""

    code = models.CharField(max_length=40, unique=True, db_index=True)
    discount_percent = models.FloatField()
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(default=1)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.discount_percent}%)"


class PromoRedemption(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="promo_redemptions")
    promo = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name="redemptions")
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "promo"]),
        ]


class ReferralCredit(models.Model):
    """One-time percent-off bucket (e.g. referrer reward after friend buys)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referral_credits")
    percent = models.FloatField()
    consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.user.username} {self.percent}% ({'used' if self.consumed else 'open'})"


class EventWaitlist(models.Model):
    STATUS_WAITING = "waiting"
    STATUS_OFFERED = "offered"
    STATUS_FULFILLED = "fulfilled"
    STATUS_MISSED = "missed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_WAITING, "Waiting"),
        (STATUS_OFFERED, "Offered"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_MISSED, "Missed payment window"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_waitlists")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="waitlist_entries")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="unique_waitlist_user_event"),
        ]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user.username} → {self.event.title} ({self.status})"


class WaitlistOffer(models.Model):
    """Single-ticket payment window after a refund frees inventory."""

    entry = models.ForeignKey(EventWaitlist, on_delete=models.CASCADE, related_name="offers")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="waitlist_offers")
    token = models.UUIDField(unique=True, db_index=True)
    unit_price_eth = models.FloatField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offer {self.token} ticket {self.ticket_id}"

class ResaleTicket(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    price_eth = models.FloatField()
    is_sold = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Resale Ticket #{self.ticket.token_id} by {self.seller.username}"

class RefundRequest(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.TextField(blank=True, null=True)
    amount_eth = models.FloatField()
    is_processed = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Refund - {self.ticket.token_id} ({self.user.username})"


class Auction(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ENDED, "Ended"),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="auctions")
    seller_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_auctions"
    )
    seller_wallet = models.CharField(max_length=200, blank=True, default="")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    highest_bid = models.FloatField(default=0)
    highest_bidder = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_auctions"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Auction #{self.id} - Ticket {self.ticket.token_id}"


class Bid(models.Model):
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bid {self.amount} ETH by {self.user.username}"

