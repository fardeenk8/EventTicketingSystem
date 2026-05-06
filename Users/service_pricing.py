from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from Admins.models import Event, Ticket
from smartcontract.blockchain_utils import contract
from Users.models import PromoCode, PromoRedemption, ReferralCredit, TicketPurchase


def get_unit_price_eth(event: Event) -> float:
    """Primary-sale unit price in ETH (matches event_pricing / on-chain when available)."""
    if contract is None:
        return float(event.price)
    try:
        chain_current = contract.functions.getCurrentPrice(event.id).call()
        return float(chain_current) / 1e18
    except Exception:
        return float(event.price)


def _promo_percent_for_user(code: str, user, event: Event) -> tuple[float, PromoCode | None]:
    if not code or not code.strip():
        return 0.0, None
    normalized = code.strip().upper()
    now = timezone.now()
    try:
        # Accept codes case-insensitively (admin entries may use lowercase).
        promo = PromoCode.objects.get(code__iexact=normalized, is_active=True)
    except PromoCode.DoesNotExist:
        return 0.0, None
    if promo.event_id and promo.event_id != event.id:
        return 0.0, None
    if not (promo.valid_from <= now <= promo.valid_until):
        return 0.0, None
    if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
        return 0.0, None
    used = PromoRedemption.objects.filter(user=user, promo=promo).count()
    if used >= promo.per_user_limit:
        return 0.0, None
    return float(promo.discount_percent), promo


def _referee_first_purchase_percent(user) -> float:
    profile = getattr(user, "profile", None)
    if not profile or not profile.referred_by_id:
        return 0.0
    if TicketPurchase.objects.filter(user=user).exists():
        return 0.0
    return 10.0


def _referral_credit_percent(user) -> float:
    credit = (
        ReferralCredit.objects.filter(user=user, consumed=False)
        .order_by("-percent")
        .first()
    )
    return float(credit.percent) if credit else 0.0


def resolve_discount_percent(user, event: Event, promo_code: str = "") -> tuple[float, PromoCode | None]:
    promo_pct, promo_obj = _promo_percent_for_user(promo_code, user, event)
    referee_pct = _referee_first_purchase_percent(user)
    credit_pct = _referral_credit_percent(user)
    raw = max(promo_pct, referee_pct, credit_pct)
    capped = min(50.0, raw)
    return capped, promo_obj


def referral_credit_was_applied(user, event: Event, promo_code: str, applied_discount: float) -> bool:
    promo_pct, _ = _promo_percent_for_user(promo_code, user, event)
    referee_pct = _referee_first_purchase_percent(user)
    credit_pct = _referral_credit_percent(user)
    if credit_pct <= 0:
        return False
    best = max(promo_pct, referee_pct, credit_pct)
    return abs(min(50.0, best) - applied_discount) < 1e-6 and credit_pct >= promo_pct and credit_pct >= referee_pct


def quote_primary_purchase(user, event: Event, quantity: int, promo_code: str = "") -> dict:
    if quantity < 1:
        quantity = 1
    unit = get_unit_price_eth(event)
    discount_pct, promo_obj = resolve_discount_percent(user, event, promo_code)
    multiplier = 1.0 - (discount_pct / 100.0)
    subtotal = unit * quantity * multiplier
    return {
        "unit_eth": unit,
        "quantity": quantity,
        "discount_percent": discount_pct,
        "total_eth": round(subtotal, 8),
        "promo_matched": promo_obj is not None,
        "promo_code": promo_obj.code if promo_obj else "",
    }


def record_promo_redemption(user, promo: PromoCode | None, event: Event) -> None:
    if promo is None:
        return
    PromoRedemption.objects.create(user=user, promo=promo, event=event)
    PromoCode.objects.filter(pk=promo.pk).update(uses_count=F("uses_count") + 1)


def record_promo_redemption_if_eligible(
    user, event: Event, promo_code: str, promo_obj: PromoCode | None, applied_discount: float
) -> None:
    """Count a promo use only when the promo code was the winning discount (not referral-only)."""
    if not promo_obj:
        return
    promo_pct, _ = _promo_percent_for_user(promo_code, user, event)
    referee_pct = _referee_first_purchase_percent(user)
    credit_pct = _referral_credit_percent(user)
    if promo_pct + 1e-9 < max(referee_pct, credit_pct):
        return
    if abs(min(50.0, max(promo_pct, referee_pct, credit_pct)) - applied_discount) > 1e-3:
        return
    record_promo_redemption(user, promo_obj, event)


def consume_referral_credit_if_used(user, event: Event, promo_code: str, discount_percent: float) -> None:
    if not referral_credit_was_applied(user, event, promo_code, discount_percent):
        return
    credit = (
        ReferralCredit.objects.filter(user=user, consumed=False)
        .order_by("-percent")
        .first()
    )
    if not credit:
        return
    credit.consumed = True
    credit.consumed_at = timezone.now()
    credit.save(update_fields=["consumed", "consumed_at"])


def grant_referrer_reward(referee) -> None:
    """After referee's first purchase, give referrer a one-time 10% credit."""
    profile = getattr(referee, "profile", None)
    if not profile or not profile.referred_by_id:
        return
    referrer = profile.referred_by
    if referrer.id == referee.id:
        return
    note = f"referral:{referee.username}"
    if ReferralCredit.objects.filter(user=referrer, note=note).exists():
        return
    ReferralCredit.objects.create(user=referrer, percent=10.0, consumed=False, note=note)
