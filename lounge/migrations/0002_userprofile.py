from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_existing_profiles(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("lounge", "UserProfile")
    database = schema_editor.connection.alias
    profiles = []
    for user in User.objects.using(database).all().iterator():
        profiles.append(UserProfile(user_id=user.pk, role="admin" if user.is_superuser else "user"))
    UserProfile.objects.using(database).bulk_create(profiles, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("lounge", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "User"), ("employee", "Employee"), ("manager", "Manager"), ("finance", "Finance"), ("admin", "Admin")], default="user", max_length=20)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user__username"]},
        ),
        migrations.RunPython(create_existing_profiles, migrations.RunPython.noop),
    ]
