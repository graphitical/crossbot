# Generated by Django 2.1.2 on 2018-11-28 16:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crossbot', '0014_onetoone_predictor'),
    ]

    operations = [
        migrations.AddField(
            model_name='cbuser',
            name='custom_title',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
    ]
