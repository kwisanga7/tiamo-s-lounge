from io import BytesIO
from functools import wraps

import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import EventForm, RegistrationForm, StaffForm, TicketPurchaseForm, UserAccountForm
from .models import Event, StaffMember, Ticket, UserProfile

User = get_user_model()


def effective_role(user):
    if user.is_superuser:
        return UserProfile.Role.ADMIN
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.role


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), login_url="login")
            if effective_role(request.user) not in allowed_roles:
                return render(request, "lounge/access_denied.html", status=403)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def account_destination(request, user):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("dashboard" if user.is_staff else "events")


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")
    role = effective_role(request.user)
    if role == UserProfile.Role.USER:
        return redirect("events" if request.user.is_authenticated else "login")
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
        "role": role,
        "user_count": User.objects.count() if role == UserProfile.Role.ADMIN else None,
    }
    return render(request, "lounge/dashboard.html", context)


def events(request):
    query = Event.objects.all()
    if not request.user.is_staff:
        query = query.filter(published=True, starts_at__gte=timezone.now())
    return render(request, "lounge/events.html", {"events": query})


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.published and not request.user.is_staff:
        return redirect("events")
    initial = {}
    if request.user.is_authenticated:
        initial = {"buyer_name": request.user.get_full_name(), "buyer_email": request.user.email}
    return render(request, "lounge/event_detail.html", {"event": event, "form": TicketPurchaseForm(initial=initial)})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
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


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def staff_list(request):
    return render(request, "lounge/staff.html", {"staff_members": StaffMember.objects.all()})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def staff_create(request):
    form = StaffForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Staff member added.")
        return redirect("staff_list")
    return render(request, "lounge/form_page.html", {"form": form, "title": "Add a team member", "eyebrow": "TEAM"})


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def ticket_list(request):
    ticket_qs = Ticket.objects.select_related("event")
    status = request.GET.get("status")
    if status in Ticket.Status.values:
        ticket_qs = ticket_qs.filter(status=status)
    return render(request, "lounge/tickets.html", {"tickets": ticket_qs, "selected_status": status})


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def mark_paid(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST" and ticket.status == Ticket.Status.PENDING:
        ticket.status = Ticket.Status.PAID
        ticket.paid_at = timezone.now()
        ticket.save(update_fields=["status", "paid_at"])
        messages.success(request, "Ticket marked paid; its QR code is now active.")
    return redirect("ticket_list")


@role_required(UserProfile.Role.EMPLOYEE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def ticket_qr(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN])
    image = qrcode.make(str(ticket.ticket_code))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@role_required(UserProfile.Role.EMPLOYEE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
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
        return account_destination(request, request.user)
    error = False
    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        username = identifier
        if "@" in identifier:
            account = User.objects.filter(email__iexact=identifier).first()
            username = account.get_username() if account else ""
        user = authenticate(request, username=username, password=request.POST.get("password"))
        if user is not None:
            login(request, user)
            return account_destination(request, user)
        error = True
    return render(request, "lounge/login.html", {
        "error": error,
        "next": request.POST.get("next") or request.GET.get("next", ""),
        "google_oauth_enabled": settings.GOOGLE_OAUTH_ENABLED,
    })


def signup_view(request):
    if request.user.is_authenticated:
        return account_destination(request, request.user)
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)
        messages.success(request, "Your account is ready. Welcome to Tiamo's Lounge!")
        return redirect("events")
    return render(request, "lounge/signup.html", {
        "form": form,
        "google_oauth_enabled": settings.GOOGLE_OAUTH_ENABLED,
    })


@role_required(UserProfile.Role.ADMIN)
def user_list(request):
    users = User.objects.select_related("profile").order_by("username")
    counts = [
        {"label": label, "count": UserProfile.objects.filter(role=role).count()}
        for role, label in UserProfile.Role.choices
    ]
    return render(request, "lounge/users.html", {"users": users, "role_counts": counts})


@role_required(UserProfile.Role.ADMIN)
def user_create(request):
    form = UserAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        messages.success(request, f"Account for {account.get_username()} created.")
        return redirect("user_list")
    return render(request, "lounge/user_form.html", {"form": form, "title": "Create account", "is_create": True})


@role_required(UserProfile.Role.ADMIN)
def user_edit(request, pk):
    account = get_object_or_404(User, pk=pk)
    form = UserAccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Account for {account.get_username()} updated.")
        return redirect("user_list")
    return render(request, "lounge/user_form.html", {"form": form, "title": f"Edit {account.get_username()}", "is_create": False, "account": account})


@role_required(UserProfile.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def user_delete(request, pk):
    account = get_object_or_404(User, pk=pk)
    if account.is_superuser:
        messages.error(request, "Superuser accounts cannot be deleted from this screen.")
        return redirect("user_list")
    if account.pk == request.user.pk:
        messages.error(request, "You cannot delete the account you are currently using.")
        return redirect("user_list")
    if request.method == "POST":
        name = account.get_username()
        account.delete()
        messages.success(request, f"Account {name} deleted.")
        return redirect("user_list")
    return render(request, "lounge/user_delete.html", {"account": account})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")
