from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0009_loungepost")]

    operations = [
        migrations.AddField(
            model_name="loungepost",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="posts/images/"),
        ),
        migrations.AddField(
            model_name="loungepost",
            name="video",
            field=models.FileField(blank=True, null=True, upload_to="posts/videos/"),
        ),
    ]
