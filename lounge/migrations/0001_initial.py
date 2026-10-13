# Initial schema for Tiamo's Lounge.
import uuid

import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=140)),
                ("description", models.TextField(blank=True)),
                ("starts_at", models.DateTimeField()),
                ("venue", models.CharField(default="Tiamo's Lounge", max_length=160)),
                ("ticket_price", models.DecimalField(decimal_places=2, max_digits=9)),
                ("capacity", models.PositiveIntegerField(default=100)),
                ("published", models.BooleanField(default=False)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["starts_at"]},
        ),
        migrations.CreateModel(
            name="StaffMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("role", models.CharField(choices=[("manager", "Manager"), ("host", "Event host"), ("bartender", "Bartender"), ("security", "Security"), ("service", "Service staff")], default="service", max_length=20)),
                ("active", models.BooleanField(default=True)),
                ("hired_on", models.DateField(default=django.utils.timezone.localdate)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("buyer_name", models.CharField(max_length=120)),
                ("buyer_email", models.EmailField(max_length=254)),
                ("ticket_code", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("pending", "Payment pending"), ("paid", "Paid"), ("checked_in", "Checked in"), ("refunded", "Refunded")], default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("checked_in_at", models.DateTimeField(blank=True, null=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tickets", to="lounge.event")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
