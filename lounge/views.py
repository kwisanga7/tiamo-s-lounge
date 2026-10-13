from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import EventForm, StaffForm, TicketPurchaseForm
from .models import Event, StaffMember, Ticket


def dashboard(request):
    today = timezone.localdate()
    upcoming = Event.objects.filter(starts_at__gte=timezone.now()).order_by("starts_at")
    context = {
        "events_count": Event.objects.count(),
        "staff_count": StaffMember.objects.filter(active=True).count(),
        "tickets_count": Ticket.objects.filter(status__in=["paid", "checked_in"]).count(),
        "pending_count": Ticket.objects.filter(status="pending").count(),
        "upcoming_events": upcoming[:4],
        "recent_tickets": Ticket.objects.select_related("event")[:5],
        "today": today,
    }
    if request.user.is_authenticated:
        return render(request, "lounge/dashboard.html", context)
    return redirect("login")


def events(request):
    query = Event.objects.all()
    if not request.user.is_authenticated:
        query = query.filter(published=True, starts_at__gte=timezone.now())
    return render(request, "lounge/events.html", {"events": query})


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.published and not request.user.is_authenticated:
        return redirect("events")
    return render(request, "lounge/event_detail.html", {"event": event, "form": TicketPurchaseForm()})


@login_required
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        event.save()
        messages.success(request, "Your event has been created.")
        return redirect("event_detail", pk=event.pk)
    return render(request, "lounge/form_page.html", {"form": form, "title": "Create an event", "eyebrow": "EVENTS"})


def buy_ticket(request, pk):
    event = get_object_or_404(Event, pk=pk, published=True)
    if event.starts_at <= timezone.now() or event.tickets_remaining < 1:
        messages.error(request, "This event is no longer accepting bookings.")
        return redirect("event_detail", pk=event.pk)
    form = TicketPurchaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.event = event
        ticket.save()
        messages.info(request, "Booking received. Your ticket is pending payment confirmation.")
        return render(request, "lounge/booking_received.html", {"ticket": ticket})
    return render(request, "lounge/event_detail.html", {"event": event, "form": form})


@login_required
def staff_list(request):
    return render(request, "lounge/staff.html", {"staff_members": StaffMember.objects.all()})


@login_required
def staff_create(request):
    form = StaffForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Staff member added.")
        return redirect("staff_list")
    return render(request, "lounge/form_page.html", {"form": form, "title": "Add a team member", "eyebrow": "TEAM"})


@login_required
def ticket_list(request):
    ticket_qs = Ticket.objects.select_related("event")
    status = request.GET.get("status")
    if status in Ticket.Status.values:
        ticket_qs = ticket_qs.filter(status=status)
    return render(request, "lounge/tickets.html", {"tickets": ticket_qs, "selected_status": status})


@login_required
def mark_paid(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST" and ticket.status == Ticket.Status.PENDING:
        ticket.status = Ticket.Status.PAID
        ticket.paid_at = timezone.now()
        ticket.save(update_fields=["status", "paid_at"])
        messages.success(request, "Ticket marked paid; its QR code is now active.")
    return redirect("ticket_list")


@login_required
def ticket_qr(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN])
    image = qrcode.make(str(ticket.ticket_code))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@login_required
def check_in(request):
    result = None
    if request.method == "POST":
        code = request.POST.get("ticket_code", "").strip()
        try:
            ticket = Ticket.objects.select_related("event").get(ticket_code=code)
        except (Ticket.DoesNotExist, ValueError):
            messages.error(request, "We couldn't find a ticket with that code.")
        else:
            if ticket.status == Ticket.Status.CHECKED_IN:
                messages.warning(request, f"{ticket.buyer_name} has already checked in.")
            elif ticket.status != Ticket.Status.PAID:
                messages.error(request, "This booking has not been paid and cannot be checked in.")
            else:
                ticket.status = Ticket.Status.CHECKED_IN
                ticket.checked_in_at = timezone.now()
                ticket.save(update_fields=["status", "checked_in_at"])
                messages.success(request, f"Welcome, {ticket.buyer_name}! Ticket checked in.")
            result = ticket
    return render(request, "lounge/check_in.html", {"result": result})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = False
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        error = True
    return render(request, "lounge/login.html", {"error": error})


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("login")
