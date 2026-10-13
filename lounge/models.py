import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    venue = models.CharField(max_length=160, default="Tiamo's Lounge")
    ticket_price = models.DecimalField(max_digits=9, decimal_places=2)
    capacity = models.PositiveIntegerField(default=100)
    published = models.BooleanField(default=False)
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
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event.title} · {self.buyer_name}"
