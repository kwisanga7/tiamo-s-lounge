from django.contrib import admin
from .models import Event, LoungePost, StaffMember, StaffShift, StaffTask, SupportRequest, Ticket, UserProfile


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


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("subject", "submitted_by", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("subject", "message", "submitted_by__username", "submitted_by__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoungePost)
class LoungePostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "notify_role", "is_published", "created_at")
    list_filter = ("notify_role", "is_published", "created_at")
    search_fields = ("title", "message", "author__username")


@admin.register(StaffTask)
class StaffTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "assigned_to", "event", "due_at", "status")
    list_filter = ("status", "event")
    search_fields = ("title", "assigned_to__name")


@admin.register(StaffShift)
class StaffShiftAdmin(admin.ModelAdmin):
    list_display = ("staff_member", "event", "starts_at", "ends_at", "checked_in_at", "checked_out_at")
    list_filter = ("event", "starts_at")
    search_fields = ("staff_member__name", "event__title")
