from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from smartcontract.blockchain_utils import contract
from Admins.models import Event, Ticket
from Users.models import TicketPurchase, ResaleTicket, RefundRequest, Auction, Bid

from django.http import JsonResponse
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

    return render(request, 'User/user_wallet.html', {
        'user': user,
        'user_wallet': user_wallet,
        'my_tickets_count': my_tickets_count,
        'upcoming_events': upcoming_events,
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

    available = Ticket.objects.filter(event=event, owner_wallet="").count()
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
        "ADMIN_ADDRESS": ADMIN_ADDRESS,
        "contract_address": contract_address
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

    user_wallet = request.user.profile.wallet
    if not user_wallet:
        return JsonResponse({
            "status": "error",
            "message": "Please connect your wallet first!"
        })

    available = Ticket.objects.filter(event=event, owner_wallet="").count()

    if quantity > available:
        return JsonResponse({
            "status": "error",
            "message": f"Only {available} tickets are available!"
        })

    tickets_to_assign = list(
        Ticket.objects.filter(event=event, owner_wallet="")[:quantity]
    )

    assigned_token_ids = []

    for t in tickets_to_assign:
        t.owner_user = request.user
        t.owner_wallet = user_wallet
        t.save()
        assigned_token_ids.append(t.token_id)

    TicketPurchase.objects.create(
        user=request.user,
        event=event,
        quantity=quantity,
        total_eth=event.price * quantity,
        tx_hash=tx_hash
    )

    return JsonResponse({
        "status": "success",
        "message": "Tickets purchased successfully!",
        "tokens": assigned_token_ids
    })

@login_required
def my_tickets(request):
    user_wallet = request.user.profile.wallet

    tickets = Ticket.objects.filter(owner_wallet=user_wallet)

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
