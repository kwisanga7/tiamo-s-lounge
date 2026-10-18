import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lounge", "0014_payroll"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="payment_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="inventorymovement",
            name="payment_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.CreateModel(
            name="FinanceObligation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("category", models.CharField(choices=[("rent", "Rent"), ("utilities", "Utilities"), ("supplier", "Supplier"), ("tax", "Tax or statutory"), ("other", "Other")], default="other", max_length=20)),
                ("due_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(choices=[("pending", "Due"), ("paid", "Paid")], default="pending", max_length=12)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["due_date", "title"]},
        ),
    ]
