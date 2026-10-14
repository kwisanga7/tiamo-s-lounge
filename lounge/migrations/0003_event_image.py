from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0002_userprofile")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="image",
            field=models.ImageField(blank=True, upload_to="events/"),
        ),
    ]
