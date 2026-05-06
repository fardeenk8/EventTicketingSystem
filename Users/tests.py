import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from Admins.models import Event, Ticket
from Users.models import (
    EventWaitlist,
    PromoCode,
    PromoRedemption,
    ReferralCredit,
    TicketPurchase,
)


class TicketingFlowsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="buyer1",
            email="buyer1@example.com",
            password="pass1234",
            is_active=True,
        )
        self.user.profile.wallet = "0x1111111111111111111111111111111111111111"
        self.user.profile.save(update_fields=["wallet"])

    def _create_event(self, title="Flow Event", total_tickets=5):
        return Event.objects.create(
            title=title,
            description="Test event",
            date=timezone.now().date() + timedelta(days=1),
            time=timezone.now().time().replace(microsecond=0),
            venue="Test Hall",
            poster="event_posters/test.jpg",
            price=10.0,
            total_tickets=total_tickets,
        )

    def test_promo_redemption_records_case_insensitive_code(self):
        event = self._create_event(title="Promo Event", total_tickets=1)
        Ticket.objects.create(event=event, token_id=1, owner_wallet="")
        PromoCode.objects.create(
            code="promo20",
            discount_percent=20,
            valid_from=timezone.now() - timedelta(hours=1),
            valid_until=timezone.now() + timedelta(hours=1),
            per_user_limit=1,
            max_uses=5,
            is_active=True,
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("buy_ticket", args=[event.id]),
            data=json.dumps({"quantity": 1, "tx_hash": "0xtest", "promo_code": "PROMO20"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")

        self.assertEqual(PromoRedemption.objects.count(), 1)
        purchase = TicketPurchase.objects.get(user=self.user, event=event)
        self.assertEqual(purchase.discount_percent_applied, 20.0)
        self.assertEqual(purchase.promo_code_used.lower(), "promo20")
        self.assertEqual(PromoCode.objects.get(code="promo20").uses_count, 1)

    def test_referral_credit_granted_then_consumed(self):
        referrer = User.objects.create_user(
            username="referrer",
            email="referrer@example.com",
            password="pass1234",
            is_active=True,
        )
        referrer.profile.wallet = "0x2222222222222222222222222222222222222222"
        referrer.profile.save(update_fields=["wallet"])

        referee = User.objects.create_user(
            username="referee",
            email="referee@example.com",
            password="pass1234",
            is_active=True,
        )
        referee.profile.wallet = "0x3333333333333333333333333333333333333333"
        referee.profile.referred_by = referrer
        referee.profile.save(update_fields=["wallet", "referred_by"])

        event_referee = self._create_event(title="Referee Event", total_tickets=1)
        Ticket.objects.create(event=event_referee, token_id=11, owner_wallet="")

        self.client.force_login(referee)
        response1 = self.client.post(
            reverse("buy_ticket", args=[event_referee.id]),
            data=json.dumps({"quantity": 1, "tx_hash": "0xref1", "promo_code": ""}),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response1.json()["status"], "success")

        credit = ReferralCredit.objects.get(user=referrer)
        self.assertEqual(credit.percent, 10.0)
        self.assertFalse(credit.consumed)

        event_referrer = self._create_event(title="Referrer Event", total_tickets=1)
        Ticket.objects.create(event=event_referrer, token_id=12, owner_wallet="")

        self.client.force_login(referrer)
        response2 = self.client.post(
            reverse("buy_ticket", args=[event_referrer.id]),
            data=json.dumps({"quantity": 1, "tx_hash": "0xref2", "promo_code": ""}),
            content_type="application/json",
        )
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.json()["status"], "success")

        credit.refresh_from_db()
        self.assertTrue(credit.consumed)
        purchase = TicketPurchase.objects.get(user=referrer, event=event_referrer)
        self.assertEqual(purchase.discount_percent_applied, 10.0)

    def test_waitlist_join_for_sold_out_event(self):
        event = self._create_event(title="Soldout Event", total_tickets=1)
        Ticket.objects.create(
            event=event,
            token_id=21,
            owner_user=self.user,
            owner_wallet="0x9999999999999999999999999999999999999999",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("join_waitlist"),
            data=json.dumps({"event_id": event.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(EventWaitlist.objects.filter(user=self.user, event=event).count(), 1)

    def test_my_tickets_includes_owner_user_when_wallet_mismatch(self):
        event = self._create_event(title="Owner User Event", total_tickets=1)
        Ticket.objects.create(
            event=event,
            token_id=31,
            owner_user=self.user,
            owner_wallet="0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("my_tickets"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner User Event")
