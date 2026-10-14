from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0006_notifications")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="profile_picture",
            field=models.ImageField(blank=True, null=True, upload_to="profiles/"),
        ),
    ]
