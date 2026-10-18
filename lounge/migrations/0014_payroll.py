import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lounge", "0013_inventory"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayrollSalary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monthly_salary", models.DecimalField(decimal_places=2, max_digits=10)),
                ("effective_from", models.DateField(default=django.utils.timezone.localdate)),
                ("active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("staff_member", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="salary_record", to="lounge.staffmember")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["staff_member__name"]},
        ),
        migrations.CreateModel(
            name="PayrollEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_start", models.DateField()),
                ("base_salary", models.DecimalField(decimal_places=2, max_digits=10)),
                ("additions", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("deductions", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("status", models.CharField(choices=[("pending", "Pending payment"), ("paid", "Paid")], default="pending", max_length=12)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("staff_member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payroll_entries", to="lounge.staffmember")),
            ],
            options={"ordering": ["staff_member__name"]},
        ),
        migrations.AddConstraint(
            model_name="payrollentry",
            constraint=models.UniqueConstraint(fields=("staff_member", "period_start"), name="unique_staff_payroll_period"),
        ),
    ]
