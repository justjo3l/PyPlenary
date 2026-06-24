from django.conf import settings
from django.db import migrations


def clear_discussions_and_non_admin_users(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Delegate = apps.get_model('councilApp', 'Delegate')
    Discussion = apps.get_model('councilApp', 'Discussion')
    PendingRego = apps.get_model('councilApp', 'PendingRego')
    ResetToken = apps.get_model('councilApp', 'ResetToken')

    Discussion.objects.all().delete()
    PendingRego.objects.all().delete()
    ResetToken.objects.all().delete()

    preserved_user_ids = set(User.objects.filter(is_superuser=True).values_list('id', flat=True))
    admin_email = getattr(settings, 'PYPLENARY_ADMIN_EMAIL', None)
    if admin_email:
        preserved_user_ids.update(User.objects.filter(username=admin_email).values_list('id', flat=True))
        preserved_user_ids.update(User.objects.filter(email=admin_email).values_list('id', flat=True))
    preserved_user_ids.update(Delegate.objects.filter(superadmin=True).values_list('authClone_id', flat=True))
    preserved_user_ids.discard(None)

    Delegate.objects.exclude(authClone_id__in=preserved_user_ids).delete()
    User.objects.exclude(id__in=preserved_user_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('councilApp', '0022_delegate_account_role_and_more'),
    ]

    operations = [
        migrations.RunPython(clear_discussions_and_non_admin_users, migrations.RunPython.noop),
    ]
