from django.contrib import admin
from .models import Event, StaffMember, Ticket


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "ticket_price", "capacity", "published")
    list_filter = ("published", "starts_at")
    search_fields = ("title", "venue")


@admin.register(StaffMember)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "email", "active")
    list_filter = ("role", "active")
    search_fields = ("name", "email")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("buyer_name", "event", "status", "created_at")
    list_filter = ("status", "event")
    search_fields = ("buyer_name", "buyer_email", "ticket_code")
    readonly_fields = ("ticket_code", "created_at", "paid_at", "checked_in_at")
