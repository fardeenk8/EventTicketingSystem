from django.contrib import admin

from Users.models import (
    EventWaitlist,
    PromoCode,
    PromoRedemption,
    ReferralCredit,
    WaitlistOffer,
)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_percent", "valid_from", "valid_until", "uses_count", "max_uses", "is_active", "event")
    list_filter = ("is_active",)
    search_fields = ("code",)


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = ("user", "promo", "event", "created_at")
    raw_id_fields = ("user", "promo", "event")


@admin.register(ReferralCredit)
class ReferralCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "percent", "consumed", "note", "created_at")
    list_filter = ("consumed",)
    raw_id_fields = ("user",)


@admin.register(EventWaitlist)
class EventWaitlistAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "status", "joined_at")
    list_filter = ("status",)
    raw_id_fields = ("user", "event")


@admin.register(WaitlistOffer)
class WaitlistOfferAdmin(admin.ModelAdmin):
    list_display = ("token", "ticket", "entry", "unit_price_eth", "expires_at", "fulfilled_at", "expired_at")
    raw_id_fields = ("ticket", "entry")
