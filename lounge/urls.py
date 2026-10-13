from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("events/", views.events, name="events"),
    path("events/new/", views.event_create, name="event_create"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/tickets/", views.buy_ticket, name="buy_ticket"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.staff_create, name="staff_create"),
    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/<int:pk>/mark-paid/", views.mark_paid, name="mark_paid"),
    path("tickets/<int:pk>/qr/", views.ticket_qr, name="ticket_qr"),
    path("check-in/", views.check_in, name="check_in"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/signup/", views.signup_view, name="signup"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),
]
