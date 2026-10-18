import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lounge", "0012_menuitem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("unit", models.CharField(default="unit", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="InventoryMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("movement_type", models.CharField(choices=[("import", "Stock received (import)"), ("sale", "Sold (export)"), ("other_out", "Other stock out")], max_length=12)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=10)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movements", to="lounge.inventoryitem")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
