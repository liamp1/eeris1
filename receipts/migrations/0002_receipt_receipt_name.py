# Generated by Django 5.1.5 on 2025-01-31 22:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('receipts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='receipt',
            name='receipt_name',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
