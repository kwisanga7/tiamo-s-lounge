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
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import EventForm, LoungePostForm, RegistrationForm, StaffForm, StaffShiftForm, StaffTaskForm, SupportRequestForm, TicketPurchaseForm, UserAccountForm, UserProfileForm
from .models import Event, LoungePost, Notification, StaffMember, StaffShift, StaffTask, SupportRequest, Ticket, UserProfile
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

    draw.text((72, 66), "TIAMO'S LOUNGE", font=font(28, True), fill="#d8b36e")
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
    draw.text((850, 535), "TIAMO'S LOUNGE  •  MEMBER CARD", font=font(18, True), fill="#d8b36e")
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
        paid_today = Ticket.objects.filter(status__in=[Ticket.Status.PAID, Ticket.Status.CHECKED_IN], paid_at__date=today)
        context.update({
            "pending_count": pending_tickets.count(),
            "paid_today_count": paid_today.count(),
            "revenue_today": paid_today.aggregate(total=Sum("event__ticket_price"))["total"] or 0,
            "pending_tickets": pending_tickets[:8],
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
        ticket.save(update_fields=["status", "paid_at"])
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
        messages.success(request, "Your account is ready. Welcome to Tiamo's Lounge!")
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
            message=f"Your Tiamo's Lounge account has been created with the {account.profile.get_role_display()} role.",
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
