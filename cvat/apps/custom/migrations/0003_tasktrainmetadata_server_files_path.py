# Generated migration for adding server_files_path field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom', '0002_taskcomment'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasktrainmetadata',
            name='server_files_path',
            field=models.CharField(
                blank=True,
                help_text='S3 prefix or server files path used for this task\'s data source',
                max_length=1024,
                null=True
            ),
        ),
    ]

