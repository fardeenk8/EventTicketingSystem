from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Event, Ticket
from smartcontract.blockchain_utils import mint_ticket, ADMIN_ADDRESS, send_eth_to_user
from django.core.paginator import Paginator
from django.http import JsonResponse
from Users.models import Profile, TicketPurchase, RefundRequest
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from django.db import models
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from web3 import Web3

def adminhome(request):
    users = User.objects.filter(is_staff=False, is_superuser=False) 
    return render(request, "Admin/adminhome.html", {"users": users})

def admin_update_userstatus(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        
        user.is_active = not user.is_active
        user.save()

        if user.is_active:
            messages.success(request, f"User {user.username} has been activated.")
        else:
            messages.success(request, f"User {user.username} has been deactivated.")
        
        return redirect('adminhome') 
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('adminhome')


@login_required
def admin_delete_user(request, user_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("adminhome")

    # Only allow staff/superuser to delete users from admin dashboard.
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "You are not authorized to delete users.")
        return redirect("adminhome")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect("adminhome")

    # Safety: avoid deleting your own logged-in admin account accidentally.
    if user.id == request.user.id:
        messages.warning(request, "You cannot delete your own account.")
        return redirect("adminhome")

    user.delete()
    messages.success(request, f"User {user.username} has been deleted.")
    return redirect("adminhome")

def create_event(request):
    if request.method == "POST":
        title = request.POST.get('title')
        description = request.POST.get('description')
        date = request.POST.get('date')
        time = request.POST.get('time')
        venue = request.POST.get('venue')
        price = request.POST.get('price')
        total_tickets = request.POST.get('total_tickets')
        poster = request.FILES.get('poster')

        Event.objects.create(
            title=title,
            description=description,
            date=date,
            time=time,
            venue=venue,
            price=price,
            total_tickets=total_tickets,
            poster=poster
        )

        messages.success(request, "Event created successfully!")
        return redirect('event_list')

    return render(request, "admin/create_event.html")

def event_list(request):
    events = Event.objects.all().order_by('-created_at')

    event_data = []
    for e in events:
        minted = Ticket.objects.filter(event=e).count()
        remaining = e.total_tickets - minted
        percentage = int((minted / e.total_tickets) * 100) if e.total_tickets > 0 else 0

        event_data.append({
            "event": e,
            "minted": minted,
            "remaining": remaining,
            "percentage": percentage,
        })

    pending_events = [ev for ev in event_data if ev["percentage"] < 100]
    completed_events = [ev for ev in event_data if ev["percentage"] == 100]

    paginator = Paginator(event_data, 5)  
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "admin/event_list.html",
        {
            "pending_events": pending_events,
            "completed_events": completed_events,
            "page_obj": page_obj,
        }
    )

def admin_mint_tickets(request, event_id):
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        messages.error(request, "Event not found!")
        return redirect('event_list')

    already_minted = Ticket.objects.filter(event=event).count()
    remaining_to_mint = event.total_tickets - already_minted

    if remaining_to_mint <= 0:
        messages.warning(request, "All tickets for this event are already minted!")
        return redirect('event_list')

    minted_ids = []
    try:
        for _ in range(remaining_to_mint):
            _, token_id = mint_ticket(event_id, ADMIN_ADDRESS)
            minted_ids.append(token_id)
            Ticket.objects.create(
                event=event,
                token_id=token_id,
                owner_user=None,
                owner_wallet=""
            )
    except Exception as e:
        messages.error(request, f"Mint failed: {str(e)}")
        return redirect('event_list')

    messages.success(
        request,
        f"Successfully minted {remaining_to_mint} tickets for event '{event.title}'!"
    )
    print("Minting", remaining_to_mint, "tickets for event", event_id)
    return redirect('event_list')

def event_tickets(request, event_id):
    event = Event.objects.get(id=event_id)
    tickets = Ticket.objects.filter(event=event).order_by("token_id")

    paginator = Paginator(tickets, 20)  
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "admin/event_tickets.html", {
        "event": event,
        "page_obj": page_obj
    })

def edit_event(request, event_id):
    event = Event.objects.get(id=event_id)

    if request.method == "POST":
        event.title = request.POST.get("title")
        event.description = request.POST.get("description")
        event.date = request.POST.get("date")
        event.time = request.POST.get("time")
        event.venue = request.POST.get("venue")
        event.price = request.POST.get("price")
        event.total_tickets = request.POST.get("total_tickets")

        if "poster" in request.FILES:
            event.poster = request.FILES["poster"]

        event.save()
        messages.success(request, "Event updated successfully!")
        return redirect("event_list")

    return render(request, "Admin/edit_event.html", {"event": event})

def delete_event(request, event_id):
    event = Event.objects.get(id=event_id)

    if request.method == "POST":
        event.delete()
        messages.success(request, "Event deleted successfully!")
        return redirect("event_list")

    return render(request, "Admin/delete_event.html", {"event": event})

def admin_qr_scanner(request):
    return render(request, "Admin/qr_scanner.html")

def validate_ticket(request):
    if request.method == "POST":
        token_id = request.POST.get("token_id")
        event_id = request.POST.get("event_id")

        try:
            ticket = Ticket.objects.get(token_id=token_id)
        except Ticket.DoesNotExist:
            return JsonResponse({
                "status": "not_found",
                "message": "Ticket not found"
            })

        if str(ticket.event.id) != str(event_id):
            return JsonResponse({
                "status": "invalid",
                "message": "Ticket does not belong to this event",
                "event": ticket.event.title
            })

        if ticket.owner_wallet == "":
            return JsonResponse({
                "status": "invalid",
                "message": "Ticket is not assigned",
            })

        user_obj = Profile.objects.filter(wallet__iexact=ticket.owner_wallet).first()
        username = user_obj.user.username if user_obj else "Unknown"

        if ticket.is_used:
            return JsonResponse({
                "status": "used",
                "message": "Ticket already used",
                "token_id": ticket.token_id,
                "event": ticket.event.title,
                "wallet": ticket.owner_wallet,
                "username": username
            })

        ticket.is_used = True
        ticket.save()

        return JsonResponse({
            "status": "valid",
            "message": "Ticket is valid and marked as used",
            "token_id": ticket.token_id,
            "event": ticket.event.title,
            "wallet": ticket.owner_wallet,
            "username": username
        })

    return JsonResponse({"status": "error", "message": "Invalid request"})

def ticket_holders(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    tickets = Ticket.objects.filter(event=event).order_by("token_id")

    ticket_list = []
    for t in tickets:
        profile = Profile.objects.filter(wallet__iexact=t.owner_wallet).first()
        username = profile.user.username if profile else "Unassigned"

        ticket_list.append({
            "token_id": t.token_id,
            "wallet": t.owner_wallet or "Not Assigned",
            "username": username,
            "is_used": t.is_used
        })

    return render(request, "admin/ticket_holders.html", {
        "event": event,
        "tickets": ticket_list
    })

def sales_report(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    total_minted = Ticket.objects.filter(event=event).count()
    total_sold = Ticket.objects.filter(event=event).exclude(owner_wallet="").count()
    total_unsold = total_minted - total_sold

    total_eth_earned = (
        TicketPurchase.objects.filter(event=event)
        .aggregate(models.Sum('total_eth'))['total_eth__sum'] or 0
    )

    purchases = TicketPurchase.objects.filter(event=event).select_related("user")

    return render(request, "admin/sales_report.html", {
        "event": event,
        "total_minted": total_minted,
        "total_sold": total_sold,
        "total_unsold": total_unsold,
        "total_eth_earned": round(total_eth_earned, 4),
        "purchases": purchases,
    })

def download_sales_report(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    total_minted = Ticket.objects.filter(event=event).count()
    total_sold = Ticket.objects.filter(event=event).exclude(owner_wallet="").count()
    total_unsold = total_minted - total_sold

    total_eth_earned = (
        TicketPurchase.objects.filter(event=event)
        .aggregate(models.Sum('total_eth'))['total_eth__sum'] or 0
    )

    purchases = TicketPurchase.objects.filter(event=event).select_related("user")

    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="sales_report_{event.id}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter

    y = height - 50
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, f"Sales Report - {event.title}")

    y -= 40
    p.setFont("Helvetica", 12)
    p.drawString(50, y, f"Total Minted Tickets: {total_minted}")
    y -= 20
    p.drawString(50, y, f"Total Sold Tickets: {total_sold}")
    y -= 20
    p.drawString(50, y, f"Unsold Tickets: {total_unsold}")
    y -= 20
    p.drawString(50, y, f"Total ETH Earned: {round(total_eth_earned, 4)} ETH")

    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, "Buyer List")
    y -= 20

    p.setFont("Helvetica", 10)
    for purchase in purchases:
        line = f"{purchase.user.username} - {purchase.quantity} tickets - {purchase.total_eth} ETH"
        p.drawString(50, y, line)
        y -= 15
        if y < 50:
            p.showPage()
            y = height - 50

    p.save()
    return response

@login_required
def admin_dashboard(request):
    total_events = Event.objects.count()

    total_minted = Ticket.objects.count()

    total_sold = Ticket.objects.exclude(owner_wallet="").count()

    total_eth_earned = (
        TicketPurchase.objects.aggregate(Sum('total_eth'))['total_eth__sum'] or 0
    )
    purchases_by_date = (
        TicketPurchase.objects
        .extra(select={'date': "date(created_at)"})
        .values('date')
        .annotate(total=Sum('quantity'))
        .order_by('date')
    )

    dates = [p['date'] for p in purchases_by_date]
    quantities = [p['total'] for p in purchases_by_date]

    eth_by_event = (
        TicketPurchase.objects
        .values('event__title')
        .annotate(total=Sum('total_eth'))
        .order_by('event__title')
    )

    event_labels = [e['event__title'] for e in eth_by_event]
    eth_values = [float(e['total']) for e in eth_by_event]

    return render(request, "Admin/dashboard.html", {
        "total_events": total_events,
        "total_minted": total_minted,
        "total_sold": total_sold,
        "total_eth_earned": round(total_eth_earned, 4),

        "dates": dates,
        "quantities": quantities,

        "event_labels": event_labels,
        "eth_values": eth_values,
    })

def refund_requests(request):
    refunds = RefundRequest.objects.all().order_by("-created_at")

    return render(request, "Admin/refund_requests.html", {
        "refunds": refunds
    })

def approve_refund(request, refund_id):
    refund = get_object_or_404(RefundRequest, id=refund_id)

    if refund.is_processed:
        messages.error(request, "Already processed.")
        return redirect("refund_requests")

    user_wallet = refund.user.profile.wallet

    if not user_wallet:
        messages.error(request, "User wallet not found.")
        return redirect("refund_requests")

    try:
        # 🔥 Convert wallet to checksum format
        user_wallet = Web3.to_checksum_address(user_wallet)
    except:
        messages.error(request, f"Invalid wallet address: {user_wallet}")
        return redirect("refund_requests")

    try:
        # Send ETH on blockchain
        tx_hash = send_eth_to_user(user_wallet, refund.amount_eth)

        # Update refund record
        refund.is_processed = True
        refund.approved = True
        refund.processed_at = timezone.now()
        refund.save()

        # Ticket becomes available again
        ticket = refund.ticket
        ticket.owner_user = None
        ticket.owner_wallet = ""  
        ticket.save()

        messages.success(request, f"Refund successful! TX: {tx_hash}")

    except Exception as e:
        messages.error(request, f"Blockchain Error: {str(e)}")

    return redirect("refund_requests")

def reject_refund(request, refund_id):
    refund = get_object_or_404(RefundRequest, id=refund_id)

    if refund.is_processed:
        messages.error(request, "Already processed.")
        return redirect("refund_requests")

    refund.is_processed = True
    refund.approved = False
    refund.processed_at = timezone.now()
    refund.save()

    messages.warning(request, "Refund request rejected.")

    return redirect("refund_requests")
