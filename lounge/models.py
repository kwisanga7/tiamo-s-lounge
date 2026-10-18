import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    venue = models.CharField(max_length=160, default="Ti'Amo's Lounge")
    image = models.ImageField(upload_to="events/", blank=True)
    ticket_price = models.DecimalField(max_digits=9, decimal_places=2)
    capacity = models.PositiveIntegerField(default=100)
    published = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    @property
    def tickets_sold(self):
        return self.tickets.filter(status__in=["paid", "checked_in"]).count()

    @property
    def tickets_remaining(self):
        return max(0, self.capacity - self.tickets.filter(status__in=["pending", "paid", "checked_in"]).count())


class MenuItem(models.Model):
    class Category(models.TextChoices):
        STARTERS = "starters", "Starters"
        MAINS = "mains", "Mains"
        DESSERTS = "desserts", "Desserts"
        COCKTAILS = "cocktails", "Cocktails"
        DRINKS = "drinks", "Drinks"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to="menu/", blank=True)
    available = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "display_order", "name"]

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    name = models.CharField(max_length=120, unique=True)
    unit = models.CharField(max_length=30, default="unit")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.unit})"


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        IMPORT = "import", "Stock received (import)"
        SALE = "sale", "Sold (export)"
        OTHER_OUT = "other_out", "Other stock out"

    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=12, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_movement_type_display()} · {self.item.name} · {self.quantity} {self.item.unit}"

    @property
    def line_value(self):
        return self.quantity * self.unit_price


class FinanceObligation(models.Model):
    class Category(models.TextChoices):
        RENT = "rent", "Rent"
        UTILITIES = "utilities", "Utilities"
        SUPPLIER = "supplier", "Supplier"
        TAX = "tax", "Tax or statutory"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Due"
        PAID = "paid", "Paid"

    title = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "title"]

    def __str__(self):
        return f"{self.title} · {self.due_date:%d %b %Y}"


class StaffMember(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        HOST = "host", "Event host"
        BARTENDER = "bartender", "Bartender"
        SECURITY = "security", "Security"
        SERVICE = "service", "Service staff"

    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SERVICE)
    active = models.BooleanField(default=True)
    hired_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} · {self.get_role_display()}"


class PayrollSalary(models.Model):
    staff_member = models.OneToOneField(StaffMember, on_delete=models.CASCADE, related_name="salary_record")
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField(default=timezone.localdate)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["staff_member__name"]

    def __str__(self):
        return f"{self.staff_member.name} · R{self.monthly_salary}/month"


class PayrollEntry(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"

    staff_member = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="payroll_entries")
    period_start = models.DateField()
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)
    additions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["staff_member__name"]
        constraints = [models.UniqueConstraint(fields=["staff_member", "period_start"], name="unique_staff_payroll_period")]

    def __str__(self):
        return f"{self.staff_member.name} · {self.period_start:%B %Y}"

    @property
    def net_pay(self):
        return self.base_salary + self.additions - self.deductions


class StaffTask(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    title = models.CharField(max_length=160)
    details = models.TextField(blank=True)
    assigned_to = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="tasks")
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_tasks")
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ASSIGNED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_staff_tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "due_at", "-created_at"]

    def __str__(self):
        return f"{self.title} · {self.assigned_to.name}"


class StaffShift(models.Model):
    staff_member = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="shifts")
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_shifts")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    notes = models.CharField(max_length=300, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_staff_shifts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "staff_member__name"]

    def __str__(self):
        return f"{self.staff_member.name} · {self.starts_at:%d %b %H:%M}"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        EMPLOYEE = "employee", "Employee"
        MANAGER = "manager", "Manager"
        FINANCE = "finance", "Finance"
        DEVELOPER = "developer", "Developer"
        ADMIN = "admin", "Admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    verification_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.get_username()} · {self.get_role_display()}"

    def save(self, *args, **kwargs):
        # Django's staff flag only opens the admin site; app permissions remain
        # controlled by this profile role and the role checks in lounge.views.
        if not self.user.is_superuser:
            should_be_staff = self.role != self.Role.USER
            if self.user.is_staff != should_be_staff:
                self.user.is_staff = should_be_staff
                self.user.save(update_fields=["is_staff"])
        super().save(*args, **kwargs)


class Ticket(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        CHECKED_IN = "checked_in", "Checked in"
        REFUNDED = "refunded", "Refunded"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tickets")
    buyer_name = models.CharField(max_length=120)
    buyer_email = models.EmailField()
    ticket_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event.title} · {self.buyer_name}"


class SupportRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="support_requests")
    subject = models.CharField(max_length=160)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_lounge_notifications")
    category = models.CharField(max_length=30, default="activity")
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"], name="notif_recipient_read_idx")]

    def __str__(self):
        return f"{self.title} · {self.recipient}"


class LoungePost(models.Model):
    class RecipientRole(models.TextChoices):
        MANAGER = UserProfile.Role.MANAGER, "Manager"
        FINANCE = UserProfile.Role.FINANCE, "Finance"
        ADMIN = UserProfile.Role.ADMIN, "Admin"

    title = models.CharField(max_length=160)
    message = models.TextField()
    image = models.ImageField(upload_to="posts/images/", blank=True, null=True)
    video = models.FileField(upload_to="posts/videos/", blank=True, null=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lounge_posts")
    notify_role = models.CharField(max_length=20, choices=RecipientRole.choices)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
