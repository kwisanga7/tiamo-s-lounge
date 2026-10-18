import csv
from datetime import date, timedelta
from io import BytesIO
from functools import wraps
from PIL import Image, ImageDraw, ImageFont, ImageOps

import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import EventForm, FinanceObligationForm, InventoryItemForm, InventoryMovementForm, LoungePostForm, MenuItemForm, PayrollPaymentForm, PayrollSalaryForm, RegistrationForm, StaffForm, StaffShiftForm, StaffTaskForm, SupportRequestForm, TicketPurchaseForm, UserAccountForm, UserProfileForm
from .models import Event, FinanceObligation, InventoryItem, InventoryMovement, LoungePost, MenuItem, Notification, PayrollEntry, PayrollSalary, StaffMember, StaffShift, StaffTask, SupportRequest, Ticket, UserProfile
from .notifications import notify_email_account, notify_roles, notify_users

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
    role = effective_role(user)
    if user.is_superuser or role != UserProfile.Role.USER:
        return redirect("dashboard")
    return redirect("home")


def _finance_period_totals(start_date, end_date):
    paid_tickets = Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN], paid_at__date__gte=start_date, paid_at__date__lte=end_date).select_related("event")
    ticket_income = sum((ticket.event.ticket_price for ticket in paid_tickets), 0)
    movements = InventoryMovement.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
    inventory_income = sum((movement.line_value for movement in movements.filter(movement_type=InventoryMovement.MovementType.SALE)), 0)
    inventory_cost = sum((movement.line_value for movement in movements.filter(movement_type=InventoryMovement.MovementType.IMPORT)), 0)
    payroll_cost = sum((entry.net_pay for entry in PayrollEntry.objects.filter(status=PayrollEntry.Status.PAID, paid_at__date__gte=start_date, paid_at__date__lte=end_date)), 0)
    obligation_cost = sum(FinanceObligation.objects.filter(status=FinanceObligation.Status.PAID, paid_at__date__gte=start_date, paid_at__date__lte=end_date).values_list("amount", flat=True), 0)
    income = ticket_income + inventory_income
    expenses = inventory_cost + payroll_cost + obligation_cost
    return {"income": income, "expenses": expenses, "net": income - expenses}


def _finance_reconciliation_flags(since_date):
    from collections import Counter

    flags = []
    refs = []
    missing = {
        "tickets": Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN], paid_at__date__gte=since_date, payment_reference="").count(),
        "inventory": InventoryMovement.objects.filter(created_at__date__gte=since_date, movement_type__in=[InventoryMovement.MovementType.IMPORT, InventoryMovement.MovementType.SALE], payment_reference="").count(),
        "payroll": PayrollEntry.objects.filter(status=PayrollEntry.Status.PAID, paid_at__date__gte=since_date, payment_reference="").count(),
        "obligations": FinanceObligation.objects.filter(status=FinanceObligation.Status.PAID, paid_at__date__gte=since_date, payment_reference="").count(),
    }
    for label, count in missing.items():
        if count:
            flags.append({"text": f"{count} recent {label} payment(s) have no reference recorded.", "url_name": "finance_ledger"})
    for model, filter_args in [
        (Ticket, {"status__in": [Ticket.Status.PAID, Ticket.Status.CHECKED_IN], "paid_at__date__gte": since_date}),
        (InventoryMovement, {"created_at__date__gte": since_date, "movement_type__in": [InventoryMovement.MovementType.IMPORT, InventoryMovement.MovementType.SALE]}),
        (PayrollEntry, {"status": PayrollEntry.Status.PAID, "paid_at__date__gte": since_date}),
        (FinanceObligation, {"status": FinanceObligation.Status.PAID, "paid_at__date__gte": since_date}),
    ]:
        refs.extend(model.objects.filter(**filter_args).exclude(payment_reference="").values_list("payment_reference", flat=True))
    duplicates = [reference for reference, count in Counter(value.strip().casefold() for value in refs if value.strip()).items() if count > 1]
    for reference in duplicates[:4]:
        flags.append({"text": f"Payment reference “{reference}” is recorded more than once.", "url_name": "finance_ledger"})
    return flags[:8]


@login_required
def post_login_redirect(request):
    return account_destination(request, request.user)


@login_required
def profile(request):
    user = request.user
    profile_form = UserProfileForm(
        request.POST if request.POST.get("form_type") == "profile" else None,
        request.FILES if request.POST.get("form_type") == "profile" else None,
        instance=user,
    )
    password_form_class = PasswordChangeForm if user.has_usable_password() else SetPasswordForm
    password_form = password_form_class(user, request.POST if request.POST.get("form_type") == "password" else None)

    if request.method == "POST" and request.POST.get("form_type") == "profile" and profile_form.is_valid():
        previous_email = user.email
        profile_form.save()
        if previous_email and previous_email.lower() != user.email.lower():
            Ticket.objects.filter(buyer_email__iexact=previous_email).update(buyer_email=user.email)
        messages.success(request, "Your profile details have been updated.")
        return redirect("profile")
    if request.method == "POST" and request.POST.get("form_type") == "password" and password_form.is_valid():
        password_form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been changed.")
        return redirect("profile")
    return render(request, "lounge/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "password_is_set": user.has_usable_password(),
        "verification_url": request.build_absolute_uri(reverse("verify_profile", kwargs={"token": user.profile.verification_token})),
        "my_lounge_posts": LoungePost.objects.filter(author=user)[:5],
    })


def lounge_posts(request):
    posts = LoungePost.objects.filter(is_published=True).select_related("author", "author__profile")
    return render(request, "lounge/posts.html", {"posts": posts})


@role_required(UserProfile.Role.EMPLOYEE, UserProfile.Role.MANAGER, UserProfile.Role.FINANCE, UserProfile.Role.ADMIN, UserProfile.Role.DEVELOPER)
def lounge_post_create(request):
    form = LoungePostForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        notify_roles(
            [post.notify_role],
            title="New lounge post needs your attention",
            message=f"{request.user.get_full_name() or request.user.get_username()} posted: {post.title}",
            url=reverse("lounge_posts"),
            category="post",
            actor=request.user,
        )
        messages.success(request, "Your update is now visible to the public, and the selected team has been notified.")
        return redirect("lounge_posts")
    return render(request, "lounge/post_form.html", {"form": form})


@login_required
def profile_qr(request):
    verification_url = request.build_absolute_uri(reverse("verify_profile", kwargs={"token": request.user.profile.verification_token}))
    image = qrcode.make(verification_url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@login_required
def profile_card_download(request):
    profile = request.user.profile
    user = request.user
    width, height = 1200, 720
    card = Image.new("RGB", (width, height), "#171715")
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=34, fill="#24221f", outline="#b9935b", width=3)

    def font(size, bold=False):
        paths = [r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    draw.text((72, 66), "TI'AMO'S LOUNGE", font=font(28, True), fill="#d8b36e")
    draw.text((72, 112), "VERIFIED MEMBER PROFILE", font=font(16, True), fill="#aaa39a")
    avatar_box = (72, 206, 332, 466)
    avatar_mask = Image.new("L", (260, 260), 0)
    ImageDraw.Draw(avatar_mask).ellipse((2, 2, 258, 258), fill=255)
    if profile.profile_picture:
        with Image.open(profile.profile_picture) as source:
            avatar = ImageOps.fit(source.convert("RGB"), (260, 260))
    else:
        avatar = Image.new("RGB", (260, 260), "#4a4031")
        initials = (user.get_full_name() or user.get_username())[:1].upper()
        ad = ImageDraw.Draw(avatar)
        bounds = ad.textbbox((0, 0), initials, font=font(100, True))
        ad.text(((260 - (bounds[2] - bounds[0])) / 2, (260 - (bounds[3] - bounds[1])) / 2 - bounds[1]), initials, font=font(100, True), fill="#f1d7a2")
    card.paste(avatar, avatar_box[:2], avatar_mask)
    draw.ellipse(avatar_box, outline="#d8b36e", width=5)
    draw.text((385, 230), user.get_full_name() or user.get_username(), font=font(44, True), fill="#fffaf2")
    draw.text((385, 304), profile.get_role_display(), font=font(27), fill="#d8b36e")
    draw.text((385, 386), "Scan to verify this active profile", font=font(20), fill="#c4bdb2")
    draw.text((385, 432), f"Member ID  {str(profile.verification_token)[:8].upper()}", font=font(17), fill="#aaa39a")
    verification_url = request.build_absolute_uri(reverse("verify_profile", kwargs={"token": profile.verification_token}))
    qr = qrcode.make(verification_url).convert("RGB").resize((260, 260))
    card.paste(qr, (850, 220))
    draw.rounded_rectangle((840, 210, 1120, 490), radius=16, outline="#d8b36e", width=4)
    draw.text((850, 535), "TI'AMO'S LOUNGE  •  MEMBER CARD", font=font(18, True), fill="#d8b36e")
    output = BytesIO()
    card.save(output, format="PNG", optimize=True)
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Content-Disposition"] = 'attachment; filename="tiamos-profile-card.png"'
    return response


def verify_profile(request, token):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), verification_token=token, user__is_active=True)
    return render(request, "lounge/profile_verification.html", {"verified_profile": profile})


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")
    role = effective_role(request.user)
    today = timezone.localdate()
    context = {"today": today, "role": role}
    if role == UserProfile.Role.ADMIN:
        context.update({
            "events_count": Event.objects.count(),
            "staff_count": StaffMember.objects.filter(active=True).count(),
            "tickets_count": Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN]).count(),
            "pending_count": Ticket.objects.filter(status=Ticket.Status.PENDING).count(),
            "user_count": User.objects.count(),
            "open_support_count": SupportRequest.objects.filter(status__in=[SupportRequest.Status.OPEN, SupportRequest.Status.IN_PROGRESS]).count(),
            "recent_tickets": Ticket.objects.select_related("event")[:5],
        })
    elif role == UserProfile.Role.MANAGER:
        upcoming = Event.objects.filter(starts_at__gte=timezone.now()).order_by("starts_at")
        context.update({
            "events_count": upcoming.count(),
            "all_event_count": Event.objects.count(),
            "staff_count": StaffMember.objects.filter(active=True).count(),
            "pending_count": Ticket.objects.filter(status=Ticket.Status.PENDING).count(),
            "open_task_count": StaffTask.objects.exclude(status=StaffTask.Status.COMPLETED).count(),
            "today_shift_count": StaffShift.objects.filter(starts_at__date=today).count(),
            "upcoming_events": upcoming[:4],
            "recent_tickets": Ticket.objects.select_related("event")[:5],
            "manager_tasks": StaffTask.objects.exclude(status=StaffTask.Status.COMPLETED).select_related("assigned_to", "event")[:5],
            "manager_shifts": StaffShift.objects.filter(starts_at__gte=timezone.now()).select_related("staff_member", "event")[:5],
        })
    elif role == UserProfile.Role.FINANCE:
        pending_tickets = Ticket.objects.filter(status=Ticket.Status.PENDING).select_related("event")
        paid_today = Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN], paid_at__date=today).select_related("event")
        month_start = today.replace(day=1)
        previous_end = month_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        previous_end = min(previous_end, previous_start + timedelta(days=today.day - 1))
        current_cash_flow = _finance_period_totals(month_start, today)
        previous_cash_flow = _finance_period_totals(previous_start, previous_end)
        obligations = FinanceObligation.objects.filter(status=FinanceObligation.Status.PENDING, due_date__lte=today + timedelta(days=30)).order_by("due_date")[:6]
        comparisons = {}
        for key in ("income", "expenses", "net"):
            current_value, previous_value = current_cash_flow[key], previous_cash_flow[key]
            comparisons[key] = {"current": current_value, "previous": previous_value, "change": current_value - previous_value}
        context.update({
            "pending_count": pending_tickets.count(),
            "paid_today_count": paid_today.count(),
            "revenue_today": paid_today.aggregate(total=Sum("event__ticket_price"))["total"] or 0,
            "pending_tickets": pending_tickets[:8],
            "paid_today_tickets": paid_today.order_by("-paid_at")[:8],
            "payroll_pending_count": PayrollEntry.objects.filter(status=PayrollEntry.Status.PENDING).count(),
            "payroll_pending_total": sum((entry.net_pay for entry in PayrollEntry.objects.filter(status=PayrollEntry.Status.PENDING)), 0),
            "current_cash_flow": current_cash_flow,
            "previous_cash_flow": previous_cash_flow,
            "cash_flow_comparisons": comparisons,
            "finance_flags": _finance_reconciliation_flags(today - timedelta(days=90)),
            "upcoming_obligations": obligations,
            "upcoming_obligation_count": obligations.count(),
            "obligations_url_name": "finance_obligations",
        })
    elif role == UserProfile.Role.EMPLOYEE:
        today_events = Event.objects.filter(starts_at__date=today, published=True).order_by("starts_at")
        checkins = Ticket.objects.filter(status=Ticket.Status.CHECKED_IN, checked_in_at__date=today).select_related("event")
        context.update({
            "today_events": today_events,
            "today_event_count": today_events.count(),
            "checkins_today": checkins.count(),
            "recent_checkins": checkins[:8],
        })
    elif role == UserProfile.Role.DEVELOPER:
        requests = SupportRequest.objects.select_related("submitted_by")
        context.update({
            "open_support_count": requests.filter(status=SupportRequest.Status.OPEN).count(),
            "in_progress_count": requests.filter(status=SupportRequest.Status.IN_PROGRESS).count(),
            "recent_support_requests": requests[:8],
        })
    else:
        tickets = Ticket.objects.select_related("event")
        if request.user.email:
            tickets = tickets.filter(buyer_email__iexact=request.user.email)
        else:
            tickets = tickets.none()
        context.update({
            "my_ticket_count": tickets.count(),
            "my_pending_count": tickets.filter(status=Ticket.Status.PENDING).count(),
            "my_paid_count": tickets.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN]).count(),
            "my_tickets": tickets[:8],
        })
    return render(request, "lounge/dashboard.html", context)


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def manager_report(request):
    today = timezone.localdate()
    start_value = request.GET.get("start", "")
    end_value = request.GET.get("end", "")
    try:
        start_date = date.fromisoformat(start_value) if start_value else today - timedelta(days=30)
        end_date = date.fromisoformat(end_value) if end_value else today
        if start_date > end_date:
            raise ValueError
    except ValueError:
        messages.error(request, "Choose a valid date range, with the start date before the end date.")
        start_date, end_date = today - timedelta(days=30), today

    events = Event.objects.filter(
        starts_at__date__gte=start_date,
        starts_at__date__lte=end_date,
    ).prefetch_related("tickets")
    rows = []
    totals = {"events": 0, "paid": 0, "checked_in": 0, "pending": 0, "refunded": 0}
    revenue = 0
    for event in events:
        tickets = list(event.tickets.all())
        paid_count = sum(ticket.status == Ticket.Status.PAID for ticket in tickets)
        checked_in_count = sum(ticket.status == Ticket.Status.CHECKED_IN for ticket in tickets)
        pending_count = sum(ticket.status == Ticket.Status.PENDING for ticket in tickets)
        refunded_count = sum(ticket.status == Ticket.Status.REFUNDED for ticket in tickets)
        paid_value = event.ticket_price * (paid_count + checked_in_count)
        rows.append({
            "event": event,
            "paid": paid_count,
            "checked_in": checked_in_count,
            "pending": pending_count,
            "refunded": refunded_count,
            "paid_value": paid_value,
        })
        totals["events"] += 1
        totals["paid"] += paid_count
        totals["checked_in"] += checked_in_count
        totals["pending"] += pending_count
        totals["refunded"] += refunded_count
        revenue += paid_value

    inventory_movements = InventoryMovement.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).select_related("item").order_by("item__name", "created_at")
    inventory_by_item = {}
    inventory_sales = 0
    imported_cost = 0
    for movement in inventory_movements:
        row = inventory_by_item.setdefault(movement.item_id, {
            "item": movement.item, "imported": 0, "sold": 0, "other_out": 0,
            "import_cost": 0, "sales": 0,
        })
        if movement.movement_type == InventoryMovement.MovementType.IMPORT:
            row["imported"] += movement.quantity
            row["import_cost"] += movement.quantity * movement.unit_price
        elif movement.movement_type == InventoryMovement.MovementType.SALE:
            row["sold"] += movement.quantity
            row["sales"] += movement.quantity * movement.unit_price
        else:
            row["other_out"] += movement.quantity
        inventory_sales += movement.quantity * movement.unit_price if movement.movement_type == InventoryMovement.MovementType.SALE else 0
        imported_cost += movement.quantity * movement.unit_price if movement.movement_type == InventoryMovement.MovementType.IMPORT else 0
    inventory_rows = list(inventory_by_item.values())
    for row in inventory_rows:
        imported_all_time = row["item"].movements.filter(movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
        exported_all_time = row["item"].movements.exclude(movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
        row["on_hand"] = imported_all_time - exported_all_time
    combined_revenue = revenue + inventory_sales

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="tiamo-report-{start_date:%Y%m%d}-{end_date:%Y%m%d}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Ti'Amo manager report", start_date.isoformat(), end_date.isoformat()])
        writer.writerow(["Events", "Paid tickets", "Checked in", "Payment pending", "Refunded", "Paid ticket value (R)", "Inventory sales (R)", "Combined recorded revenue (R)", "Inventory import cost (R)"])
        writer.writerow([totals["events"], totals["paid"], totals["checked_in"], totals["pending"], totals["refunded"], f"{revenue:.2f}", f"{inventory_sales:.2f}", f"{combined_revenue:.2f}", f"{imported_cost:.2f}"])
        writer.writerow([])
        writer.writerow(["Event", "Date", "Capacity", "Paid tickets", "Checked in", "Payment pending", "Refunded", "Paid ticket value (R)"])
        for row in rows:
            writer.writerow([
                row["event"].title, row["event"].starts_at.strftime("%Y-%m-%d %H:%M"), row["event"].capacity,
                row["paid"], row["checked_in"], row["pending"], row["refunded"], f"{row['paid_value']:.2f}",
            ])
        writer.writerow([])
        writer.writerow(["Inventory summary", "Unit", "Imported in range", "Sold in range", "Other stock out", "Sales (R)", "Import cost (R)", "Current stock on hand"])
        for row in inventory_rows:
            writer.writerow([row["item"].name, row["item"].unit, row["imported"], row["sold"], row["other_out"], f"{row['sales']:.2f}", f"{row['import_cost']:.2f}", row["on_hand"]])
        writer.writerow([])
        writer.writerow(["Inventory movement details", "Type", "Item", "Quantity", "Unit", "Unit price/cost (R)", "Line value (R)", "Recorded at", "Reference", "Note"])
        for movement in inventory_movements:
            writer.writerow([movement.get_movement_type_display(), movement.movement_type, movement.item.name, movement.quantity, movement.item.unit, f"{movement.unit_price:.2f}", f"{movement.quantity * movement.unit_price:.2f}", timezone.localtime(movement.created_at).strftime("%Y-%m-%d %H:%M"), movement.payment_reference, movement.note])
        return response

    return render(request, "lounge/manager_report.html", {
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
        "totals": totals,
        "revenue": revenue,
        "inventory_rows": inventory_rows,
        "inventory_sales": inventory_sales,
        "imported_cost": imported_cost,
        "combined_revenue": combined_revenue,
        "inventory_movements": inventory_movements,
    })


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.ADMIN)
def finance_report(request):
    today = timezone.localdate()
    try:
        start_date = date.fromisoformat(request.GET["start"]) if request.GET.get("start") else today - timedelta(days=30)
        end_date = date.fromisoformat(request.GET["end"]) if request.GET.get("end") else today
        if start_date > end_date:
            raise ValueError
    except ValueError:
        messages.error(request, "Choose a valid date range, with the start date before the end date.")
        start_date, end_date = today - timedelta(days=30), today

    paid_tickets = Ticket.objects.filter(
        status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN],
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    ).select_related("event").order_by("-paid_at")
    ticket_rows = list(paid_tickets)
    ticket_revenue = sum((ticket.event.ticket_price for ticket in ticket_rows), 0)
    movements = list(InventoryMovement.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).select_related("item").order_by("-created_at"))
    inventory_sales = sum((movement.line_value for movement in movements if movement.movement_type == InventoryMovement.MovementType.SALE), 0)
    inventory_costs = sum((movement.line_value for movement in movements if movement.movement_type == InventoryMovement.MovementType.IMPORT), 0)
    recorded_sales = ticket_revenue + inventory_sales
    payroll_rows = list(PayrollEntry.objects.filter(
        status=PayrollEntry.Status.PAID,
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    ).select_related("staff_member").order_by("-paid_at"))
    payroll_paid = sum((entry.net_pay for entry in payroll_rows), 0)
    obligation_rows = list(FinanceObligation.objects.filter(
        status=FinanceObligation.Status.PAID,
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    ).order_by("-paid_at"))
    obligations_paid = sum((item.amount for item in obligation_rows), 0)

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="tiamo-finance-{start_date:%Y%m%d}-{end_date:%Y%m%d}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Ti'Amo finance report", start_date.isoformat(), end_date.isoformat()])
        writer.writerow(["Paid tickets", "Ticket value (R)", "Inventory sales (R)", "Recorded sales (R)", "Inventory import cost (R)", "Payroll paid (R)", "Obligations paid (R)"])
        writer.writerow([len(ticket_rows), f"{ticket_revenue:.2f}", f"{inventory_sales:.2f}", f"{recorded_sales:.2f}", f"{inventory_costs:.2f}", f"{payroll_paid:.2f}", f"{obligations_paid:.2f}"])
        writer.writerow([])
        writer.writerow(["Ticket payments", "Paid at", "Guest", "Email", "Event", "Amount (R)", "Status"])
        for ticket in ticket_rows:
            writer.writerow([ticket.ticket_code, timezone.localtime(ticket.paid_at).strftime("%Y-%m-%d %H:%M") if ticket.paid_at else "", ticket.buyer_name, ticket.buyer_email, ticket.event.title, f"{ticket.event.ticket_price:.2f}", ticket.get_status_display()])
        writer.writerow([])
        writer.writerow(["Inventory movements", "Recorded at", "Movement", "Item", "Quantity", "Unit", "Unit price/cost (R)", "Value (R)", "Reference", "Note"])
        for movement in movements:
            writer.writerow([movement.movement_type, timezone.localtime(movement.created_at).strftime("%Y-%m-%d %H:%M"), movement.get_movement_type_display(), movement.item.name, movement.quantity, movement.item.unit, f"{movement.unit_price:.2f}", f"{movement.line_value:.2f}", movement.payment_reference, movement.note])
        writer.writerow([])
        writer.writerow(["Payroll payments", "Paid at", "Pay period", "Staff member", "Base salary (R)", "Additions (R)", "Deductions (R)", "Net paid (R)", "Reference"])
        for entry in payroll_rows:
            writer.writerow([entry.pk, timezone.localtime(entry.paid_at).strftime("%Y-%m-%d %H:%M"), entry.period_start.strftime("%B %Y"), entry.staff_member.name, f"{entry.base_salary:.2f}", f"{entry.additions:.2f}", f"{entry.deductions:.2f}", f"{entry.net_pay:.2f}", entry.payment_reference])
        writer.writerow([])
        writer.writerow(["Paid obligations", "Paid at", "Category", "Description", "Amount (R)", "Reference", "Note"])
        for item in obligation_rows:
            writer.writerow([item.pk, timezone.localtime(item.paid_at).strftime("%Y-%m-%d %H:%M"), item.get_category_display(), item.title, f"{item.amount:.2f}", item.payment_reference, item.note])
        return response

    return render(request, "lounge/finance_report.html", {
        "start_date": start_date, "end_date": end_date,
        "ticket_rows": ticket_rows, "ticket_count": len(ticket_rows),
        "ticket_revenue": ticket_revenue, "inventory_sales": inventory_sales,
        "inventory_costs": inventory_costs, "recorded_sales": recorded_sales,
        "movements": movements,
        "payroll_rows": payroll_rows, "payroll_paid": payroll_paid,
        "obligation_rows": obligation_rows, "obligations_paid": obligations_paid,
    })


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.ADMIN)
def finance_obligations(request):
    form = FinanceObligationForm()
    if request.method == "POST" and request.POST.get("action") == "add":
        form = FinanceObligationForm(request.POST)
        if form.is_valid():
            obligation = form.save(commit=False)
            obligation.created_by = request.user
            obligation.save()
            messages.success(request, "Upcoming obligation recorded.")
            return redirect("finance_obligations")
    elif request.method == "POST" and request.POST.get("action") == "mark_paid":
        obligation = get_object_or_404(FinanceObligation, pk=request.POST.get("obligation_id"), status=FinanceObligation.Status.PENDING)
        obligation.status = FinanceObligation.Status.PAID
        obligation.paid_at = timezone.now()
        obligation.payment_reference = request.POST.get("payment_reference", "").strip()
        obligation.save(update_fields=["status", "paid_at", "payment_reference"])
        messages.success(request, f"{obligation.title} marked paid.")
        return redirect("finance_obligations")
    today = timezone.localdate()
    obligations = FinanceObligation.objects.all()
    return render(request, "lounge/finance_obligations.html", {
        "form": form,
        "today": today,
        "obligations": obligations,
        "upcoming": obligations.filter(status=FinanceObligation.Status.PENDING, due_date__lte=today + timedelta(days=30)),
        "pending_total": sum(obligations.filter(status=FinanceObligation.Status.PENDING).values_list("amount", flat=True), 0),
    })


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.ADMIN)
def finance_ledger(request):
    today = timezone.localdate()
    try:
        start_date = date.fromisoformat(request.GET["start"]) if request.GET.get("start") else today.replace(day=1)
        end_date = date.fromisoformat(request.GET["end"]) if request.GET.get("end") else today
        if start_date > end_date:
            raise ValueError
    except ValueError:
        messages.error(request, "Choose a valid date range, with the start date before the end date.")
        start_date, end_date = today.replace(day=1), today

    rows = []
    tickets = Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN], paid_at__date__gte=start_date, paid_at__date__lte=end_date).select_related("event")
    for ticket in tickets:
        rows.append({"when": ticket.paid_at, "type": "Ticket receipt", "description": f"{ticket.event.title} · {ticket.buyer_name}", "income": ticket.event.ticket_price, "expense": 0, "reference": ticket.payment_reference, "note": ticket.buyer_email})
    movements = InventoryMovement.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date).select_related("item")
    for movement in movements:
        if movement.movement_type == InventoryMovement.MovementType.SALE:
            income, expense = movement.line_value, 0
        else:
            income, expense = 0, movement.line_value
        rows.append({"when": movement.created_at, "type": movement.get_movement_type_display(), "description": f"{movement.item.name} · {movement.quantity} {movement.item.unit}", "income": income, "expense": expense, "reference": movement.payment_reference, "note": movement.note})
    payroll = PayrollEntry.objects.filter(status=PayrollEntry.Status.PAID, paid_at__date__gte=start_date, paid_at__date__lte=end_date).select_related("staff_member")
    for entry in payroll:
        rows.append({"when": entry.paid_at, "type": "Payroll", "description": f"{entry.staff_member.name} · {entry.period_start:%B %Y}", "income": 0, "expense": entry.net_pay, "reference": entry.payment_reference, "note": "Salary payment"})
    obligations = FinanceObligation.objects.filter(status=FinanceObligation.Status.PAID, paid_at__date__gte=start_date, paid_at__date__lte=end_date)
    for obligation in obligations:
        rows.append({"when": obligation.paid_at, "type": obligation.get_category_display(), "description": obligation.title, "income": 0, "expense": obligation.amount, "reference": obligation.payment_reference, "note": obligation.note})
    rows.sort(key=lambda row: row["when"] or timezone.now(), reverse=True)
    total_income = sum((row["income"] for row in rows), 0)
    total_expense = sum((row["expense"] for row in rows), 0)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="tiamo-ledger-{start_date:%Y%m%d}-{end_date:%Y%m%d}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Ti'Amo payment ledger", start_date.isoformat(), end_date.isoformat()])
        writer.writerow(["Recorded at", "Type", "Description", "Money in (R)", "Money out (R)", "Reference", "Note"])
        for row in rows:
            writer.writerow([timezone.localtime(row["when"]).strftime("%Y-%m-%d %H:%M") if row["when"] else "", row["type"], row["description"], f"{row['income']:.2f}", f"{row['expense']:.2f}", row["reference"], row["note"]])
        writer.writerow(["TOTAL", "", "", f"{total_income:.2f}", f"{total_expense:.2f}", "", ""])
        return response
    return render(request, "lounge/finance_ledger.html", {
        "start_date": start_date, "end_date": end_date, "rows": rows,
        "total_income": total_income, "total_expense": total_expense,
        "cash_change": total_income - total_expense,
        "flags": _finance_reconciliation_flags(start_date),
    })


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.ADMIN)
def finance_members(request):
    visible_roles = [
        UserProfile.Role.EMPLOYEE,
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
        UserProfile.Role.DEVELOPER,
    ]
    members = UserProfile.objects.filter(role__in=visible_roles).select_related("user")
    role_filter = request.GET.get("role", "")
    if role_filter in visible_roles:
        members = members.filter(role=role_filter)
    query = request.GET.get("q", "").strip()
    if query:
        members = members.filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
        )
    return render(request, "lounge/finance_members.html", {
        "members": members,
        "role_filter": role_filter,
        "search_query": query,
        "role_choices": [(role, UserProfile.Role(role).label) for role in visible_roles],
        "member_count": members.count(),
    })


@role_required(UserProfile.Role.FINANCE, UserProfile.Role.ADMIN)
def finance_payroll(request):
    today = timezone.localdate()
    period_value = request.POST.get("period", "") if request.method == "POST" else request.GET.get("period", "")
    try:
        period_start = date.fromisoformat(f"{period_value}-01") if period_value else today.replace(day=1)
    except ValueError:
        messages.error(request, "Choose a valid payroll month.")
        period_start = today.replace(day=1)
    salary_form = PayrollSalaryForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_salary":
            existing = PayrollSalary.objects.filter(staff_member_id=request.POST.get("staff_member")).first()
            salary_form = PayrollSalaryForm(request.POST, instance=existing)
            if salary_form.is_valid():
                salary = salary_form.save(commit=False)
                salary.updated_by = request.user
                salary.save()
                messages.success(request, f"Salary for {salary.staff_member.name} was saved.")
                return redirect(f"{reverse('finance_payroll')}?period={period_start:%Y-%m}")
        elif action == "generate":
            created = 0
            with transaction.atomic():
                period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                salaries = PayrollSalary.objects.filter(active=True, staff_member__active=True, effective_from__lte=period_end).select_related("staff_member")
                for salary in salaries:
                    _, was_created = PayrollEntry.objects.get_or_create(
                        staff_member=salary.staff_member,
                        period_start=period_start,
                        defaults={"base_salary": salary.monthly_salary, "created_by": request.user},
                    )
                    created += int(was_created)
            messages.success(request, f"Payroll created for {period_start:%B %Y}: {created} new staff entries.")
            return redirect(f"{reverse('finance_payroll')}?period={period_start:%Y-%m}")
        elif action == "mark_paid":
            entry = get_object_or_404(PayrollEntry, pk=request.POST.get("entry_id"), period_start=period_start)
            if entry.status == PayrollEntry.Status.PENDING:
                payment_form = PayrollPaymentForm(request.POST, base_salary=entry.base_salary)
                if payment_form.is_valid():
                    entry.additions = payment_form.cleaned_data.get("additions") or 0
                    entry.deductions = payment_form.cleaned_data.get("deductions") or 0
                    entry.payment_reference = payment_form.cleaned_data.get("payment_reference", "")
                    entry.status = PayrollEntry.Status.PAID
                    entry.paid_at = timezone.now()
                    entry.save(update_fields=["additions", "deductions", "payment_reference", "status", "paid_at"])
                    messages.success(request, f"Payroll for {entry.staff_member.name} marked paid.")
                    return redirect(f"{reverse('finance_payroll')}?period={period_start:%Y-%m}")
                messages.error(request, "Review the payroll adjustments. Net pay must remain greater than zero.")

    entries = list(PayrollEntry.objects.filter(period_start=period_start).select_related("staff_member"))
    for entry in entries:
        entry.payment_form = PayrollPaymentForm(
            base_salary=entry.base_salary,
            initial={"additions": entry.additions, "deductions": entry.deductions, "payment_reference": entry.payment_reference},
        )
    salaries = PayrollSalary.objects.select_related("staff_member").all()
    return render(request, "lounge/finance_payroll.html", {
        "period_start": period_start,
        "entries": entries,
        "salaries": salaries,
        "salary_form": salary_form,
        "pending_total": sum((entry.net_pay for entry in entries if entry.status == PayrollEntry.Status.PENDING), 0),
        "paid_total": sum((entry.net_pay for entry in entries if entry.status == PayrollEntry.Status.PAID), 0),
        "pending_count": sum(entry.status == PayrollEntry.Status.PENDING for entry in entries),
        "paid_count": sum(entry.status == PayrollEntry.Status.PAID for entry in entries),
    })


def home(request):
    public_events = list(Event.objects.filter(published=True).order_by("starts_at"))
    now = timezone.now()
    featured_event = next((event for event in public_events if event.starts_at >= now), None)
    if featured_event is None and public_events:
        featured_event = public_events[0]
    return render(request, "lounge/home.html", {
        "events": public_events,
        "featured_event": featured_event,
        "featured_is_upcoming": bool(featured_event and featured_event.starts_at >= now),
        "is_home": True,
    })


def events(request):
    query = Event.objects.all()
    can_manage_events = request.user.is_authenticated and effective_role(request.user) in [
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    ]
    if not can_manage_events:
        query = query.filter(published=True)
    return render(request, "lounge/events.html", {"events": query})


def menu_page(request):
    can_manage = request.user.is_authenticated and effective_role(request.user) in [UserProfile.Role.MANAGER, UserProfile.Role.ADMIN]
    items = MenuItem.objects.all() if can_manage else MenuItem.objects.filter(available=True)
    sections = []
    for value, label in MenuItem.Category.choices:
        section_items = items.filter(category=value)
        if section_items.exists():
            sections.append({"label": label, "items": section_items})
    return render(request, "lounge/menu.html", {"sections": sections, "can_manage_menu": can_manage})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def manager_inventory(request):
    item_form = InventoryItemForm(prefix="item")
    movement_form = InventoryMovementForm(prefix="movement")
    if request.method == "POST" and request.POST.get("form_type") == "item":
        item_form = InventoryItemForm(request.POST, prefix="item")
        if item_form.is_valid():
            item_form.save()
            messages.success(request, "Inventory item added. Record a stock import to add it to your stock on hand.")
            return redirect("manager_inventory")
    elif request.method == "POST":
        movement_form = InventoryMovementForm(request.POST, prefix="movement")
        if movement_form.is_valid():
            with transaction.atomic():
                movement = movement_form.save(commit=False)
                item = InventoryItem.objects.select_for_update().get(pk=movement.item_id)
                imported = InventoryMovement.objects.filter(item=item, movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
                exported = InventoryMovement.objects.filter(item=item).exclude(movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
                available = imported - exported
                if movement.movement_type != InventoryMovement.MovementType.IMPORT and movement.quantity > available:
                    movement_form.add_error("quantity", f"Only {available} {item.unit} are currently in stock.")
                else:
                    movement.created_by = request.user
                    movement.save()
                    messages.success(request, "Inventory movement recorded.")
                    return redirect("manager_inventory")

    stock_rows = []
    for item in InventoryItem.objects.all():
        imported = item.movements.filter(movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
        exported = item.movements.exclude(movement_type=InventoryMovement.MovementType.IMPORT).aggregate(total=Sum("quantity"))["total"] or 0
        stock_rows.append({"item": item, "on_hand": imported - exported})
    recent_movements = InventoryMovement.objects.select_related("item", "created_by")[:25]
    return render(request, "lounge/manager_inventory.html", {
        "item_form": item_form,
        "movement_form": movement_form,
        "stock_rows": stock_rows,
        "recent_movements": recent_movements,
    })


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def menu_item_create(request):
    form = MenuItemForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"{item.name} was added to the menu.")
        return redirect("menu_page")
    return render(request, "lounge/menu_item_form.html", {"form": form, "title": "Add menu item", "is_create": True})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def menu_item_edit(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    form = MenuItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{item.name} was updated.")
        return redirect("menu_page")
    return render(request, "lounge/menu_item_form.html", {"form": form, "title": f"Edit {item.name}", "is_create": False, "item": item})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
@require_POST
def menu_item_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    name = item.name
    item.delete()
    messages.success(request, f"{name} was removed from the menu.")
    return redirect("menu_page")


@login_required
def support_center(request):
    form = SupportRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        support_request = form.save(commit=False)
        support_request.submitted_by = request.user
        support_request.save()
        notify_roles(
            [UserProfile.Role.DEVELOPER, UserProfile.Role.ADMIN],
            title="New support request",
            message=f"{request.user.get_username()} submitted: {support_request.subject}",
            url="/support/",
            category="support",
            actor=request.user,
        )
        messages.success(request, "Your support request has been sent to the support team.")
        return redirect("support_center")

    role = effective_role(request.user)
    requests = SupportRequest.objects.select_related("submitted_by")
    if role not in [UserProfile.Role.DEVELOPER, UserProfile.Role.ADMIN]:
        requests = requests.filter(submitted_by=request.user)
    return render(request, "lounge/support_center.html", {
        "form": form,
        "support_requests": requests,
        "can_manage_support": role in [UserProfile.Role.DEVELOPER, UserProfile.Role.ADMIN],
    })


@role_required(UserProfile.Role.DEVELOPER, UserProfile.Role.ADMIN)
@require_POST
def support_request_update(request, pk):
    support_request = get_object_or_404(SupportRequest, pk=pk)
    status = request.POST.get("status")
    if status in SupportRequest.Status.values:
        previous_status = support_request.status
        support_request.status = status
        support_request.save(update_fields=["status", "updated_at"])
        if previous_status != status and support_request.submitted_by_id:
            notify_users(
                [support_request.submitted_by],
                title="Support request updated",
                message=f"{support_request.subject} is now {support_request.get_status_display().lower()}.",
                url="/support/",
                category="support",
                actor=request.user,
            )
        messages.success(request, "Support request status updated.")
    else:
        messages.error(request, "Choose a valid support request status.")
    return redirect("support_center")


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(request, "lounge/notifications.html", {"notifications": notifications})


@login_required
def notification_open(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    target = notification.url
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect("notification_list")


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect("notification_list")


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    can_manage_events = request.user.is_authenticated and effective_role(request.user) in [
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    ]
    if not event.published and not can_manage_events:
        return redirect("events")
    initial = {}
    if request.user.is_authenticated:
        initial = {"buyer_name": request.user.get_full_name(), "buyer_email": request.user.email}
    return render(request, "lounge/event_detail.html", {"event": event, "form": TicketPurchaseForm(initial=initial), "now": timezone.now()})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def event_create(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        event.save()
        if event.published:
            notify_roles(
                [UserProfile.Role.ADMIN],
                title="Event published",
                message=f"{event.title} is now listed for guests.",
                url=f"/events/{event.pk}/",
                category="event",
                actor=request.user,
            )
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
        notify_email_account(
            ticket.buyer_email,
            title="Booking received",
            message=f"Your booking for {event.title} is awaiting payment confirmation.",
            url=f"/events/{event.pk}/",
            category="booking",
            actor=request.user if request.user.is_authenticated else None,
        )
        notify_roles(
            [UserProfile.Role.FINANCE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN],
            title="Booking needs payment confirmation",
            message=f"{ticket.buyer_name} booked {event.title}.",
            url="/tickets/",
            category="booking",
            actor=request.user if request.user.is_authenticated else None,
        )
        messages.info(request, "Booking received. Your ticket is pending payment confirmation.")
        return render(request, "lounge/booking_received.html", {"ticket": ticket})
    return render(request, "lounge/event_detail.html", {"event": event, "form": form, "now": timezone.now()})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def staff_list(request):
    return render(request, "lounge/staff.html", {"staff_members": StaffMember.objects.all()})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def staff_create(request):
    form = StaffForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        notify_roles(
            [UserProfile.Role.ADMIN, UserProfile.Role.MANAGER],
            title="Team member added",
            message=f"{member.name} was added to the lounge team.",
            url="/staff/",
            category="team",
            actor=request.user,
        )
        messages.success(request, "Staff member added.")
        return redirect("staff_list")
    return render(request, "lounge/form_page.html", {"form": form, "title": "Add a team member", "eyebrow": "TEAM"})


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def team_operations(request):
    task_form = StaffTaskForm(prefix="task")
    shift_form = StaffShiftForm(prefix="shift")
    staff_members = StaffMember.objects.all()
    tasks = StaffTask.objects.select_related("assigned_to", "event", "created_by")[:30]
    upcoming_shifts = StaffShift.objects.filter(Q(ends_at__gte=timezone.now()) | Q(checked_in_at__isnull=False, checked_out_at__isnull=True)).select_related("staff_member", "event")[:30]
    recent_attendance = StaffShift.objects.filter(checked_in_at__isnull=False).select_related("staff_member", "event").order_by("-checked_in_at")[:30]
    all_events = Event.objects.order_by("-starts_at")
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "task":
            task_form = StaffTaskForm(request.POST, prefix="task")
            if task_form.is_valid():
                task = task_form.save(commit=False)
                task.created_by = request.user
                task.save()
                messages.success(request, f"Task assigned to {task.assigned_to.name}.")
                return redirect("team_operations")
        elif form_type == "shift":
            shift_form = StaffShiftForm(request.POST, prefix="shift")
            if shift_form.is_valid():
                shift = shift_form.save(commit=False)
                shift.created_by = request.user
                shift.save()
                messages.success(request, f"Shift scheduled for {shift.staff_member.name}.")
                return redirect("team_operations")
    return render(request, "lounge/team_operations.html", {
        "task_form": task_form,
        "shift_form": shift_form,
        "staff_members": staff_members,
        "tasks": tasks,
        "upcoming_shifts": upcoming_shifts,
        "recent_attendance": recent_attendance,
        "all_events": all_events,
    })


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
@require_POST
def staff_task_status(request, pk):
    task = get_object_or_404(StaffTask, pk=pk)
    status = request.POST.get("status")
    if status in StaffTask.Status.values:
        task.status = status
        task.save(update_fields=["status"])
        messages.success(request, f"Task status updated for {task.assigned_to.name}.")
    else:
        messages.error(request, "Choose a valid task status.")
    return redirect("team_operations")


@role_required(UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
@require_POST
def staff_shift_attendance(request, pk, action):
    shift = get_object_or_404(StaffShift.objects.select_related("staff_member"), pk=pk)
    now = timezone.now()
    if action == "check-in":
        if shift.checked_in_at:
            messages.warning(request, f"{shift.staff_member.name} is already checked in for this shift.")
        else:
            shift.checked_in_at = now
            shift.save(update_fields=["checked_in_at"])
            messages.success(request, f"{shift.staff_member.name} checked in at {timezone.localtime(now):%I:%M %p}.")
    elif action == "check-out":
        if not shift.checked_in_at:
            messages.error(request, "Record a check-in before checking out.")
        elif shift.checked_out_at:
            messages.warning(request, f"{shift.staff_member.name} is already checked out for this shift.")
        else:
            shift.checked_out_at = now
            shift.save(update_fields=["checked_out_at"])
            messages.success(request, f"{shift.staff_member.name} checked out at {timezone.localtime(now):%I:%M %p}.")
    else:
        messages.error(request, "Unknown attendance action.")
    return redirect("team_operations")


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
        ticket.payment_reference = request.POST.get("payment_reference", "").strip()
        ticket.save(update_fields=["status", "paid_at", "payment_reference"])
        notify_email_account(
            ticket.buyer_email,
            title="Payment confirmed",
            message=f"Payment for {ticket.event.title} has been confirmed by the lounge team.",
            url=f"/events/{ticket.event_id}/",
            category="payment",
            actor=request.user,
        )
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
                notify_email_account(
                    ticket.buyer_email,
                    title="You checked in",
                    message=f"Your ticket for {ticket.event.title} was scanned at the lounge.",
                    url=f"/events/{ticket.event_id}/",
                    category="check_in",
                    actor=request.user,
                )
                messages.success(request, f"Welcome, {ticket.buyer_name}! Ticket checked in.")
            result = ticket
    return render(request, "lounge/check_in.html", {"result": result})


@role_required(UserProfile.Role.EMPLOYEE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
def guest_list(request):
    today = timezone.localdate()
    available_events = Event.objects.filter(published=True, starts_at__date__gte=today).order_by("starts_at")
    event_id = request.GET.get("event")
    if event_id:
        selected_event = get_object_or_404(available_events, pk=event_id)
    else:
        selected_event = available_events.filter(starts_at__date=today).first() or available_events.first()

    tickets = Ticket.objects.none()
    search = request.GET.get("q", "").strip()
    if selected_event:
        tickets = Ticket.objects.filter(event=selected_event).select_related("event")
        if search:
            tickets = tickets.filter(buyer_name__icontains=search)
    return render(request, "lounge/guest_list.html", {
        "events": available_events,
        "selected_event": selected_event,
        "tickets": tickets,
        "search": search,
        "paid_count": tickets.filter(status=Ticket.Status.PAID).count(),
        "checked_in_count": tickets.filter(status=Ticket.Status.CHECKED_IN).count(),
    })


@role_required(UserProfile.Role.EMPLOYEE, UserProfile.Role.MANAGER, UserProfile.Role.ADMIN)
@require_POST
def check_in_ticket(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("event"), pk=pk)
    if ticket.status == Ticket.Status.CHECKED_IN:
        messages.warning(request, f"{ticket.buyer_name} has already checked in.")
    elif ticket.status != Ticket.Status.PAID:
        messages.error(request, "This booking has not been paid and cannot be checked in.")
    else:
        ticket.status = Ticket.Status.CHECKED_IN
        ticket.checked_in_at = timezone.now()
        ticket.save(update_fields=["status", "checked_in_at"])
        notify_email_account(
            ticket.buyer_email,
            title="You checked in",
            message=f"Your ticket for {ticket.event.title} was scanned at the lounge.",
            url=f"/events/{ticket.event_id}/",
            category="check_in",
            actor=request.user,
        )
        messages.success(request, f"Welcome, {ticket.buyer_name}! Ticket checked in.")
    return redirect(f"{reverse('guest_list')}?event={ticket.event_id}")


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
        messages.success(request, "Your account is ready. Welcome to Ti'Amo's Lounge!")
        return redirect("home")
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
        notify_users(
            [account],
            title="Your lounge account is ready",
            message=f"Your Ti'Amo's Lounge account has been created with the {account.profile.get_role_display()} role.",
            url="/accounts/login/",
            category="account",
            actor=request.user,
        )
        messages.success(request, f"Account for {account.get_username()} created.")
        return redirect("user_list")
    return render(request, "lounge/user_form.html", {"form": form, "title": "Create account", "is_create": True})


@role_required(UserProfile.Role.ADMIN)
def user_edit(request, pk):
    account = get_object_or_404(User, pk=pk)
    form = UserAccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        previous_role = account.profile.role
        form.save()
        if account.profile.role != previous_role:
            notify_users(
                [account],
                title="Your lounge role changed",
                message=f"Your account now has the {account.profile.get_role_display()} role.",
                url="/accounts/post-login/",
                category="account",
                actor=request.user,
            )
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
