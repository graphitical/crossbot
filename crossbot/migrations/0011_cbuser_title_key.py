# Generated by Django 2.1.2 on 2018-11-01 02:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crossbot', '0010_fix_time_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='cbuser',
            name='title_key',
            field=models.CharField(max_length=20, null=True),
        ),
    ]
