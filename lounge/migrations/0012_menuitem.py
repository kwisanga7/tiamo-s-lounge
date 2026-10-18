from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0011_staff_tasks_shifts")]

    operations = [
        migrations.CreateModel(
            name="MenuItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(choices=[("starters", "Starters"), ("mains", "Mains"), ("desserts", "Desserts"), ("cocktails", "Cocktails"), ("drinks", "Drinks"), ("other", "Other")], default="other", max_length=20)),
                ("price", models.DecimalField(decimal_places=2, max_digits=8)),
                ("image", models.ImageField(blank=True, upload_to="menu/")),
                ("available", models.BooleanField(default=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["category", "display_order", "name"]},
        ),
    ]
