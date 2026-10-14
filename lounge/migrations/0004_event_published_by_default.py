from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0003_event_image")]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="published",
            field=models.BooleanField(default=True),
        ),
    ]
