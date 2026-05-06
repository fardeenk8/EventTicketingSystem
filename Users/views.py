import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.views.decorators.http import require_POST
from smartcontract.blockchain_utils import contract
from Admins.models import Event, Ticket
from Users.models import (
    TicketPurchase,
    ResaleTicket,
    RefundRequest,
    Auction,
    Bid,
    EventWaitlist,
    WaitlistOffer,
)
from Users.service_pricing import (
    quote_primary_purchase,
    record_promo_redemption_if_eligible,
    consume_referral_credit_if_used,
    grant_referrer_reward,
    resolve_discount_percent,
)
from Users.service_waitlist import (
    available_tickets_queryset,
    expire_stale_waitlist_offers,
    WAITLIST_PAYMENT_MINUTES,
)

from django.http import HttpResponseForbidden, JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from smartcontract.blockchain_utils import ADMIN_ADDRESS
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import os

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import qrcode
from io import BytesIO
from django.http import HttpResponse
from web3 import Web3

def userhome(request):
    user = request.user
    return render(request, 'User/userhome.html', {'user':user})

@login_required
def user_wallet(request):
    user = request.user
    user_wallet = ""

    if hasattr(user, 'profile'):
        user_wallet = user.profile.wallet

    my_tickets_count = (
        Ticket.objects.filter(owner_wallet__iexact=user_wallet).count()
        if user_wallet else 0
    )

    upcoming_events = Event.objects.all().order_by('date')[:4]
    referral_code = ""
    if hasattr(user, "profile"):
        referral_code = (user.profile.referral_code or "").strip()

    return render(request, 'User/user_wallet.html', {
        'user': user,
        'user_wallet': user_wallet,
        'my_tickets_count': my_tickets_count,
        'upcoming_events': upcoming_events,
        'referral_code': referral_code,
    })

@login_required
@csrf_exempt
def save_wallet(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            wallet = data.get("wallet", "").strip()

            if wallet:
                try:
                    wallet = Web3.to_checksum_address(wallet)
                except:
                    return JsonResponse({"status": "error", "message": "Invalid wallet address"}, status=400)

                profile = request.user.profile
                profile.wallet = wallet
                profile.save()
                return JsonResponse({"status": "ok"})

            return JsonResponse({"status": "error", "message": "No wallet provided"}, status=400)

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "bad_request"}, status=400)

def browse_events(request):
    events = Event.objects.all().order_by('-created_at')
    return render(request, 'User/browse_events.html', {'events': events})


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    expire_stale_waitlist_offers()
    available = available_tickets_queryset(event).count()

    waitlist_status = None
    waitlist_position = None
    waitlist_pay_path = None
    if request.user.is_authenticated:
        wl = EventWaitlist.objects.filter(user=request.user, event=event).first()
        if wl:
            waitlist_status = wl.status
            if wl.status == EventWaitlist.STATUS_WAITING:
                waitlist_position = EventWaitlist.objects.filter(
                    event=event,
                    status=EventWaitlist.STATUS_WAITING,
                    joined_at__lte=wl.joined_at,
                ).count()
            if wl.status == EventWaitlist.STATUS_OFFERED:
                offer = (
                    WaitlistOffer.objects.filter(
                        entry=wl,
                        fulfilled_at__isnull=True,
                        expired_at__isnull=True,
                        expires_at__gte=timezone.now(),
                    )
                    .order_by("-created_at")
                    .first()
                )
                if offer:
                    waitlist_pay_path = f"/Users/waitlist/pay/{offer.token}/"

    contract_address = ""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ticket_json_path = os.path.join(base_dir, "smartcontract", "TicketNFT.json")
        with open(ticket_json_path, "r") as f:
            contract_data = json.load(f)
            contract_address = (contract_data.get("address") or "").strip()
    except Exception:
        contract_address = ""

    return render(request, "User/event_detail.html", {
        "event": event,
        "remaining": available,
        "sold_out": available == 0,
        "ADMIN_ADDRESS": ADMIN_ADDRESS,
        "contract_address": contract_address,
        "waitlist_status": waitlist_status,
        "waitlist_position": waitlist_position,
        "waitlist_pay_path": waitlist_pay_path,
        "checkout_quote_enabled": request.user.is_authenticated,
    })


def event_pricing(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    tickets_sold_db = Ticket.objects.filter(event=event).exclude(owner_wallet="").count()

    base_price = float(event.price)
    current_price = float(event.price)
    price_increment = 0.0
    dynamic_enabled = False

    # If contract is deployed and pricing exists on-chain, prefer on-chain pricing.
    if contract is not None:
        try:
            chain_current = contract.functions.getCurrentPrice(event_id).call()
            pricing_tuple = contract.functions.eventPricing(event_id).call()
            # pricing_tuple = (basePrice, priceIncrement, ticketsSold)
            base_price = float(pricing_tuple[0])
            price_increment = float(pricing_tuple[1])
            tickets_sold = int(pricing_tuple[2])
            current_price = float(chain_current)
            dynamic_enabled = True
        except Exception:
            tickets_sold = tickets_sold_db
    else:
        tickets_sold = tickets_sold_db

    return JsonResponse({
        "status": "success",
        "event_id": event.id,
        "base_price": base_price,
        "current_price": current_price,
        "price_increment": price_increment,
        "tickets_sold": tickets_sold,
        "dynamic_enabled": dynamic_enabled
    })

@login_required
@csrf_exempt
def buy_ticket(request, event_id):

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request."})

    event = get_object_or_404(Event, id=event_id)

    data = json.loads(request.body)

    quantity = int(data.get("quantity", 1))
    tx_hash = data.get("tx_hash")
    promo_code = (data.get("promo_code") or "").strip()

    user_wallet = request.user.profile.wallet
    if not user_wallet:
        return JsonResponse({
            "status": "error",
            "message": "Please connect your wallet first!"
        })

    expire_stale_waitlist_offers()
    qs = available_tickets_queryset(event)
    available = qs.count()

    if quantity > available:
        return JsonResponse({
            "status": "error",
            "message": f"Only {available} tickets are available!"
        })

    quote = quote_primary_purchase(request.user, event, quantity, promo_code)
    discount_pct, promo_obj = resolve_discount_percent(request.user, event, promo_code)
    is_first_purchase = not TicketPurchase.objects.filter(user=request.user).exists()

    tickets_to_assign = list(qs[:quantity])

    assigned_token_ids = []

    with transaction.atomic():
        for t in tickets_to_assign:
            locked = Ticket.objects.select_for_update().get(pk=t.pk)
            if locked.owner_wallet:
                return JsonResponse({
                    "status": "error",
                    "message": "Inventory changed — fewer tickets available. Refresh and try again.",
                })
            locked.owner_user = request.user
            locked.owner_wallet = user_wallet
            locked.save()
            assigned_token_ids.append(locked.token_id)

        TicketPurchase.objects.create(
            user=request.user,
            event=event,
            quantity=quantity,
            total_eth=quote["total_eth"],
            tx_hash=tx_hash or "",
            promo_code_used=(promo_obj.code if promo_obj else ""),
            discount_percent_applied=discount_pct,
        )
        record_promo_redemption_if_eligible(
            request.user, event, promo_code, promo_obj, discount_pct
        )
        consume_referral_credit_if_used(request.user, event, promo_code, discount_pct)
        if is_first_purchase:
            grant_referrer_reward(request.user)

    return JsonResponse({
        "status": "success",
        "message": "Tickets purchased successfully!",
        "tokens": assigned_token_ids
    })


@login_required
@csrf_exempt
@require_POST
def checkout_quote(request):
    """JSON quote for primary checkout (MetaMask amount + discounts)."""
    try:
        data = json.loads(request.body)
        event_id = int(data.get("event_id"))
        quantity = max(1, int(data.get("quantity", 1)))
        promo_code = (data.get("promo_code") or "").strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload."}, status=400)

    event = get_object_or_404(Event, id=event_id)
    expire_stale_waitlist_offers()
    avail = available_tickets_queryset(event).count()
    quote = quote_primary_purchase(request.user, event, quantity, promo_code)
    discount_pct, _ = resolve_discount_percent(request.user, event, promo_code)

    return JsonResponse({
        "status": "success",
        "available": avail,
        "can_buy": avail >= quantity,
        "unit_eth": quote["unit_eth"],
        "total_eth": quote["total_eth"],
        "discount_percent": discount_pct,
        "promo_matched": quote["promo_matched"],
    })


@login_required
@csrf_exempt
@require_POST
def join_waitlist(request):
    try:
        data = json.loads(request.body)
        event_id = int(data.get("event_id"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload."}, status=400)

    event = get_object_or_404(Event, id=event_id)
    expire_stale_waitlist_offers()

    if available_tickets_queryset(event).count() > 0:
        return JsonResponse(
            {"status": "error", "message": "Tickets are still available — purchase from the event page."},
            status=400,
        )

    entry = EventWaitlist.objects.filter(user=request.user, event=event).first()
    if entry:
        if entry.status == EventWaitlist.STATUS_WAITING:
            pos = EventWaitlist.objects.filter(
                event=event,
                status=EventWaitlist.STATUS_WAITING,
                joined_at__lte=entry.joined_at,
            ).count()
            return JsonResponse(
                {"status": "ok", "message": "You are already on the waitlist.", "position": pos}
            )
        if entry.status == EventWaitlist.STATUS_FULFILLED:
            return JsonResponse(
                {"status": "error", "message": "You already completed a waitlist purchase for this event."},
                status=400,
            )
        if entry.status == EventWaitlist.STATUS_OFFERED:
            offer = (
                WaitlistOffer.objects.filter(
                    entry=entry,
                    fulfilled_at__isnull=True,
                    expired_at__isnull=True,
                    expires_at__gte=timezone.now(),
                )
                .order_by("-created_at")
                .first()
            )
            if offer:
                return JsonResponse(
                    {
                        "status": "ok",
                        "message": "You have an active payment window.",
                        "pay_url": f"/Users/waitlist/pay/{offer.token}/",
                    }
                )
            entry.delete()
            EventWaitlist.objects.create(
                user=request.user,
                event=event,
                status=EventWaitlist.STATUS_WAITING,
            )
            pos = EventWaitlist.objects.filter(event=event, status=EventWaitlist.STATUS_WAITING).count()
            return JsonResponse({"status": "ok", "message": "Re-joined the waitlist.", "position": pos})
        if entry.status in (EventWaitlist.STATUS_MISSED, EventWaitlist.STATUS_CANCELLED):
            entry.delete()

    EventWaitlist.objects.create(
        user=request.user,
        event=event,
        status=EventWaitlist.STATUS_WAITING,
    )
    pos = EventWaitlist.objects.filter(event=event, status=EventWaitlist.STATUS_WAITING).count()
    return JsonResponse({"status": "ok", "message": "Joined the waitlist.", "position": pos})


@login_required
@csrf_exempt
@require_POST
def leave_waitlist(request):
    try:
        data = json.loads(request.body)
        event_id = int(data.get("event_id"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload."}, status=400)

    event = get_object_or_404(Event, id=event_id)
    updated = EventWaitlist.objects.filter(
        user=request.user,
        event=event,
        status=EventWaitlist.STATUS_WAITING,
    ).update(status=EventWaitlist.STATUS_CANCELLED)
    if updated:
        return JsonResponse({"status": "ok", "message": "Removed from waitlist."})
    return JsonResponse({"status": "error", "message": "Not on waitlist (or you have an active offer)."}, status=400)


@login_required
def waitlist_pay_page(request, token):
    expire_stale_waitlist_offers()
    offer = get_object_or_404(WaitlistOffer.objects.select_related("ticket", "ticket__event", "entry"), token=token)

    if offer.entry.user_id != request.user.id:
        return HttpResponseForbidden("This waitlist link belongs to another account.")

    now = timezone.now()
    if offer.fulfilled_at or offer.expired_at or offer.expires_at < now:
        return render(
            request,
            "User/waitlist_expired.html",
            {"event": offer.ticket.event, "minutes": WAITLIST_PAYMENT_MINUTES},
        )

    if offer.ticket.owner_wallet:
        return render(
            request,
            "User/waitlist_expired.html",
            {"event": offer.ticket.event, "minutes": WAITLIST_PAYMENT_MINUTES},
        )

    event = offer.ticket.event
    discount_pct, _ = resolve_discount_percent(request.user, event, "")

    return render(
        request,
        "User/waitlist_pay.html",
        {
            "offer": offer,
            "event": event,
            "ticket": offer.ticket,
            "ADMIN_ADDRESS": ADMIN_ADDRESS,
            "snapshot_unit_eth": offer.unit_price_eth,
            "discount_percent": discount_pct,
            "total_eth": round(offer.unit_price_eth * (1.0 - discount_pct / 100.0), 8),
            "minutes": WAITLIST_PAYMENT_MINUTES,
            "expires_at_iso": offer.expires_at.isoformat(),
        },
    )


def _read_contract_address():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ticket_json_path = os.path.join(base_dir, "smartcontract", "TicketNFT.json")
        with open(ticket_json_path, "r") as f:
            return (json.load(f).get("address") or "").strip()
    except Exception:
        return ""


@login_required
@csrf_exempt
@require_POST
def waitlist_checkout_quote(request):
    """Quote for waitlist payment window (uses snapshot unit price from the offer)."""
    try:
        data = json.loads(request.body)
        token = uuid.UUID(str(data.get("token")))
        promo_code = (data.get("promo_code") or "").strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload."}, status=400)

    offer = get_object_or_404(
        WaitlistOffer.objects.select_related("ticket", "ticket__event", "entry"),
        token=token,
    )
    if offer.entry.user_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Forbidden."}, status=403)

    expire_stale_waitlist_offers()
    offer.refresh_from_db()
    now = timezone.now()
    if offer.fulfilled_at or offer.expired_at or offer.expires_at < now:
        return JsonResponse({"status": "error", "message": "Offer expired."}, status=400)

    event = offer.ticket.event
    discount_pct, _ = resolve_discount_percent(request.user, event, promo_code)
    unit = float(offer.unit_price_eth)
    total = round(unit * (1.0 - discount_pct / 100.0), 8)

    return JsonResponse(
        {
            "status": "success",
            "unit_eth": unit,
            "total_eth": total,
            "discount_percent": discount_pct,
            "expires_at": offer.expires_at.isoformat(),
        }
    )


@login_required
@csrf_exempt
@require_POST
def buy_waitlist_ticket(request):
    try:
        data = json.loads(request.body)
        token = uuid.UUID(str(data.get("token")))
        tx_hash = data.get("tx_hash") or ""
        promo_code = (data.get("promo_code") or "").strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload."}, status=400)

    user_wallet = request.user.profile.wallet
    if not user_wallet:
        return JsonResponse({"status": "error", "message": "Please connect your wallet first!"})

    expire_stale_waitlist_offers()

    with transaction.atomic():
        offer = (
            WaitlistOffer.objects.select_for_update()
            .select_related("ticket", "ticket__event", "entry")
            .filter(token=token)
            .first()
        )
        if not offer:
            return JsonResponse({"status": "error", "message": "Offer not found."}, status=404)

        if offer.entry.user_id != request.user.id:
            return JsonResponse({"status": "error", "message": "Forbidden."}, status=403)

        now = timezone.now()
        if offer.fulfilled_at or offer.expired_at or offer.expires_at < now:
            return JsonResponse({"status": "error", "message": "This payment window has expired."}, status=400)

        ticket = Ticket.objects.select_for_update().get(pk=offer.ticket_id)
        if ticket.owner_wallet:
            return JsonResponse({"status": "error", "message": "This ticket is no longer available."}, status=400)

        event = ticket.event
        discount_pct, promo_obj = resolve_discount_percent(request.user, event, promo_code)
        total_eth = round(offer.unit_price_eth * (1.0 - discount_pct / 100.0), 8)
        is_first_purchase = not TicketPurchase.objects.filter(user=request.user).exists()

        ticket.owner_user = request.user
        ticket.owner_wallet = user_wallet
        ticket.save()

        offer.fulfilled_at = now
        offer.save(update_fields=["fulfilled_at"])

        offer.entry.status = EventWaitlist.STATUS_FULFILLED
        offer.entry.save(update_fields=["status"])

        TicketPurchase.objects.create(
            user=request.user,
            event=event,
            quantity=1,
            total_eth=total_eth,
            tx_hash=tx_hash,
            promo_code_used=(promo_obj.code if promo_obj else ""),
            discount_percent_applied=discount_pct,
        )
        record_promo_redemption_if_eligible(
            request.user, event, promo_code, promo_obj, discount_pct
        )
        consume_referral_credit_if_used(request.user, event, promo_code, discount_pct)
        if is_first_purchase:
            grant_referrer_reward(request.user)

    return JsonResponse(
        {
            "status": "success",
            "message": "Ticket purchased successfully!",
            "tokens": [ticket.token_id],
        }
    )

@login_required
def my_tickets(request):
    user_wallet = request.user.profile.wallet

    # Prefer explicit user ownership; keep wallet match for older records.
    tickets = (
        Ticket.objects.filter(
            Q(owner_user=request.user) |
            Q(owner_wallet__iexact=user_wallet)
        )
        .distinct()
        .order_by("-id")
    )

    return render(request, "User/my_tickets.html", {
        "tickets": tickets
    })

def download_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    event = ticket.event
    wallet = request.user.profile.wallet

    qr_data = f"TOKEN:{ticket.token_id}|EVENT:{event.id}"
    qr_img = qrcode.make(qr_data)
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="ticket_{ticket.token_id}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, f"Event Ticket - {event.title}")

    try:
        poster_img = ImageReader(event.poster.path)
        p.drawImage(poster_img, 50, height - 350, width=200, height=250)
    except:
        pass

    p.setFont("Helvetica", 12)
    p.drawString(300, height - 120, f"Date: {event.date}")
    p.drawString(300, height - 140, f"Time: {event.time}")
    p.drawString(300, height - 160, f"Venue: {event.venue}")
    p.drawString(300, height - 200, f"Wallet: {wallet}")
    p.drawString(300, height - 220, f"Token ID: {ticket.token_id}")

    qr_image = ImageReader(qr_buffer)
    p.drawImage(qr_image, 300, height - 450, width=180, height=180)

    p.setFont("Helvetica-Oblique", 10)
    p.drawString(50, 50, "Generated by Event Management DApp")

    p.save()
    return response

@login_required
def transaction_history(request):
    purchases = TicketPurchase.objects.filter(user=request.user).order_by('-created_at')

    return render(request, "User/transaction_history.html", {
        "purchases": purchases
    })

@login_required
def resale_ticket(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request"})

    data = json.loads(request.body)
    ticket_id = data.get("ticket_id")
    price_eth = float(data.get("price_eth", 0))

    if price_eth <= 0:
        return JsonResponse({"status": "error", "message": "Invalid price"})

    ticket = Ticket.objects.get(id=ticket_id)
    user_wallet = request.user.profile.wallet.lower()

    # Check ownership
    if ticket.owner_wallet.lower() != user_wallet:
        return JsonResponse({"status": "error", "message": "You don't own this ticket!"})

    # Check if already listed
    resale, created = ResaleTicket.objects.get_or_create(
        ticket=ticket,
        defaults={
            "seller": request.user,
            "price_eth": price_eth
        }
    )

    if not created:
        resale.price_eth = price_eth
        resale.save()

    return JsonResponse({"status": "success", "message": "Ticket listed for resale!"})

@login_required
def marketplace(request):
    listings = ResaleTicket.objects.filter(is_sold=False)
    contract_address = ""
    auction_supported = False
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ticket_json_path = os.path.join(base_dir, "smartcontract", "TicketNFT.json")
        with open(ticket_json_path, "r") as f:
            contract_data = json.load(f)
            contract_address = (contract_data.get("address") or "").strip()
            abi = contract_data.get("abi") or []
            method_names = {item.get("name") for item in abi if item.get("type") == "function"}
            auction_supported = "placeBid" in method_names
    except Exception:
        contract_address = ""
        auction_supported = False

    current_wallet = ""
    if hasattr(request.user, "profile"):
        current_wallet = (request.user.profile.wallet or "").strip()

    return render(request, "User/marketplace.html", {
        "listings": listings,
        "contract_address": contract_address,
        "auction_supported": auction_supported,
        "current_username": request.user.username,
        "current_wallet": current_wallet
    })

@login_required
def buy_resale_ticket(request, resale_id):
    listing = ResaleTicket.objects.get(id=resale_id)

    if listing.is_sold:
        return JsonResponse({"status": "error", "message": "This ticket is already sold!"})

    buyer_wallet = request.user.profile.wallet

    if not buyer_wallet:
        return JsonResponse({"status": "error", "message": "Please connect your wallet first!"})

    # Prevent buying your own ticket
    if listing.seller == request.user:
        return JsonResponse({"status": "error", "message": "You cannot buy your own listing!"})

    ticket = listing.ticket

    # Update ticket ownership
    ticket.owner_user = request.user
    ticket.owner_wallet = buyer_wallet
    ticket.save()

    # Mark resale listing as sold
    listing.is_sold = True
    listing.save()

    return JsonResponse({"status": "success", "message": "Ticket purchased successfully!"})

@login_required
def refund_ticket(request):
    data = json.loads(request.body)
    ticket_id = data.get("ticket_id")
    reason = data.get("reason")

    ticket = Ticket.objects.get(id=ticket_id)

    # validate ownership
    if ticket.owner_wallet.lower() != request.user.profile.wallet.lower():
        return JsonResponse({"status": "error", "message": "You do not own this ticket."})

    # used tickets cannot be refunded
    if ticket.is_used:
        return JsonResponse({"status": "error", "message": "Used tickets cannot be refunded."})

    RefundRequest.objects.get_or_create(
        ticket=ticket,
        user=request.user,
        defaults={
            "reason": reason,
            "amount_eth": ticket.event.price
        }
    )

    return JsonResponse({"status": "success", "message": "Refund request submitted!"})


@login_required
@csrf_exempt
def create_auction(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
        ticket_id = data.get("ticket_id")
        start_time_raw = data.get("start_time")
        end_time_raw = data.get("end_time")

        if not ticket_id or not start_time_raw or not end_time_raw:
            return JsonResponse({"status": "error", "message": "ticket_id, start_time and end_time are required"}, status=400)

        ticket = get_object_or_404(Ticket, id=ticket_id)
        user_wallet = (request.user.profile.wallet or "").lower()

        if not user_wallet or ticket.owner_wallet.lower() != user_wallet:
            return JsonResponse({"status": "error", "message": "Only ticket owner can create auction"}, status=403)

        start_time = parse_datetime(start_time_raw)
        end_time = parse_datetime(end_time_raw)
        if not start_time or not end_time:
            return JsonResponse({"status": "error", "message": "Invalid datetime format. Use ISO format"}, status=400)

        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)

        now = timezone.now()
        if end_time <= start_time:
            return JsonResponse({"status": "error", "message": "end_time must be after start_time"}, status=400)
        if end_time <= now:
            return JsonResponse({"status": "error", "message": "end_time must be in the future"}, status=400)

        has_active = Auction.objects.filter(ticket=ticket, status=Auction.STATUS_ACTIVE).exists()
        if has_active:
            return JsonResponse({"status": "error", "message": "This ticket already has an active auction"}, status=400)

        auction = Auction.objects.create(
            ticket=ticket,
            seller_user=request.user,
            seller_wallet=(request.user.profile.wallet or ""),
            start_time=start_time,
            end_time=end_time,
            highest_bid=0,
            highest_bidder=None,
            status=Auction.STATUS_ACTIVE
        )

        return JsonResponse({
            "status": "success",
            "auction_id": auction.id,
            "ticket_id": auction.ticket.id
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@csrf_exempt
def place_bid(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
        auction_id = data.get("auction_id")
        amount = float(data.get("amount", 0))

        if not auction_id or amount <= 0:
            return JsonResponse({"status": "error", "message": "auction_id and valid amount are required"}, status=400)

        auction = get_object_or_404(Auction, id=auction_id)
        now = timezone.now()

        if auction.status != Auction.STATUS_ACTIVE:
            return JsonResponse({"status": "error", "message": "Auction is not active"}, status=400)
        if now < auction.start_time:
            return JsonResponse({"status": "error", "message": "Auction has not started yet"}, status=400)
        if now > auction.end_time:
            auction.status = Auction.STATUS_ENDED
            auction.save(update_fields=["status"])
            return JsonResponse({"status": "error", "message": "Auction has already ended"}, status=400)
        if amount <= auction.highest_bid:
            return JsonResponse({"status": "error", "message": "Bid must be higher than current highest bid"}, status=400)

        bid = Bid.objects.create(
            auction=auction,
            user=request.user,
            amount=amount
        )

        auction.highest_bid = amount
        auction.highest_bidder = request.user
        auction.save(update_fields=["highest_bid", "highest_bidder"])

        return JsonResponse({
            "status": "success",
            "auction_id": auction.id,
            "bid_id": bid.id,
            "highest_bid": auction.highest_bid,
            "highest_bidder": request.user.username
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def auction_details(request, auction_id):
    auction = get_object_or_404(Auction, id=auction_id)

    if auction.status == Auction.STATUS_ACTIVE and timezone.now() > auction.end_time:
        auction.status = Auction.STATUS_ENDED
        auction.save(update_fields=["status"])

    bids = auction.bids.select_related("user").order_by("-amount", "-timestamp")

    return JsonResponse({
        "status": "success",
        "auction": {
            "id": auction.id,
            "ticket_id": auction.ticket.id,
            "token_id": auction.ticket.token_id,
            "seller_username": auction.seller_user.username if auction.seller_user else None,
            "seller_wallet": auction.seller_wallet,
            "start_time": auction.start_time.isoformat(),
            "end_time": auction.end_time.isoformat(),
            "highest_bid": auction.highest_bid,
            "highest_bidder": auction.highest_bidder.username if auction.highest_bidder else None,
            "status": auction.status
        },
        "bids": [
            {
                "id": b.id,
                "user": b.user.username,
                "amount": b.amount,
                "timestamp": b.timestamp.isoformat()
            }
            for b in bids
        ]
    })


@login_required
def auction_list(request):
    now = timezone.now()
    include_ended = request.GET.get("include_ended", "false").lower() == "true"

    Auction.objects.filter(status=Auction.STATUS_ACTIVE, end_time__lt=now).update(status=Auction.STATUS_ENDED)

    queryset = Auction.objects.select_related("ticket", "ticket__event", "highest_bidder", "seller_user").order_by("-created_at")
    if not include_ended:
        queryset = queryset.filter(status=Auction.STATUS_ACTIVE)

    auctions = []
    for a in queryset:
        legacy_seller_match = (a.seller_user_id is None and a.ticket.owner_user_id == request.user.id)
        can_end_now = (
            a.status == Auction.STATUS_ACTIVE
            and a.highest_bidder is not None
            and (
                a.seller_user_id == request.user.id
                or legacy_seller_match
            )
        )
        auctions.append({
            "id": a.id,
            "ticket_id": a.ticket.id,
            "token_id": a.ticket.token_id,
            "event_id": a.ticket.event.id,
            "event_title": a.ticket.event.title,
            "poster_url": a.ticket.event.poster.url if a.ticket.event.poster else "",
            "seller_username": a.seller_user.username if a.seller_user else (a.ticket.owner_user.username if a.ticket.owner_user else None),
            "seller_wallet": a.seller_wallet or a.ticket.owner_wallet,
            "start_time": a.start_time.isoformat(),
            "end_time": a.end_time.isoformat(),
            "highest_bid": a.highest_bid,
            "highest_bidder": a.highest_bidder.username if a.highest_bidder else None,
            "status": a.status,
            "can_end_now": can_end_now
        })

    return JsonResponse({"status": "success", "auctions": auctions})


@login_required
@csrf_exempt
def end_auction_now(request, auction_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

    auction = get_object_or_404(Auction, id=auction_id)

    if auction.status != Auction.STATUS_ACTIVE:
        return JsonResponse({"status": "error", "message": "Auction is not active"}, status=400)

    # Backward compatibility for auctions created before seller_user field existed.
    if auction.seller_user_id is None:
        if auction.ticket.owner_user_id != request.user.id:
            return JsonResponse({"status": "error", "message": "Only seller can end this auction"}, status=403)
        auction.seller_user = request.user
        auction.seller_wallet = auction.ticket.owner_wallet or auction.seller_wallet
        auction.save(update_fields=["seller_user", "seller_wallet"])
    elif auction.seller_user_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Only seller can end this auction"}, status=403)

    if not auction.highest_bidder:
        return JsonResponse({"status": "error", "message": "Cannot end auction without bids"}, status=400)

    ticket = auction.ticket
    buyer_profile = getattr(auction.highest_bidder, "profile", None)
    buyer_wallet = buyer_profile.wallet if buyer_profile else ""
    if not buyer_wallet:
        return JsonResponse({"status": "error", "message": "Highest bidder has no connected wallet"}, status=400)

    ticket.owner_user = auction.highest_bidder
    ticket.owner_wallet = buyer_wallet
    ticket.save(update_fields=["owner_user", "owner_wallet"])

    auction.status = Auction.STATUS_ENDED
    auction.save(update_fields=["status"])

    return JsonResponse({
        "status": "success",
        "message": "Auction ended. Ticket transferred to highest bidder.",
        "winner": auction.highest_bidder.username,
        "ticket_id": ticket.id
    })
