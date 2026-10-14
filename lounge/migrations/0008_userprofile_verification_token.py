import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lounge", "0007_userprofile_profile_picture")]

    def populate_tokens(apps, schema_editor):
        UserProfile = apps.get_model("lounge", "UserProfile")
        for profile in UserProfile.objects.filter(verification_token__isnull=True).iterator():
            profile.verification_token = uuid.uuid4()
            profile.save(update_fields=["verification_token"])

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="verification_token",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="verification_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
