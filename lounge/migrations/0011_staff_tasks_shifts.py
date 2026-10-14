from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lounge", "0010_loungepost_media"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("details", models.TextField(blank=True)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("assigned", "Assigned"), ("in_progress", "In progress"), ("completed", "Completed")], default="assigned", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assigned_to", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="lounge.staffmember")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_staff_tasks", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_tasks", to="lounge.event")),
            ],
            options={"ordering": ["status", "due_at", "-created_at"]},
        ),
        migrations.CreateModel(
            name="StaffShift",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("checked_in_at", models.DateTimeField(blank=True, null=True)),
                ("checked_out_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_staff_shifts", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_shifts", to="lounge.event")),
                ("staff_member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shifts", to="lounge.staffmember")),
            ],
            options={"ordering": ["starts_at", "staff_member__name"]},
        ),
    ]
