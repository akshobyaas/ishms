from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='TelemetryReading',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp',    models.DateTimeField(auto_now_add=True)),
                ('cpu',          models.FloatField()),
                ('memory',       models.FloatField()),
                ('temperature',  models.FloatField()),
                ('power',        models.FloatField()),
                ('temp_source',  models.CharField(default='fallback', max_length=20)),
                ('power_source', models.CharField(default='fallback', max_length=20)),
                ('status',       models.CharField(
                    choices=[
                        ('Normal',                   'Normal'),
                        ('Suspicious',               'Suspicious'),
                        ('Confirmed Anomaly',        'Confirmed Anomaly'),
                        ('Memory Leak Suspected',    'Memory Leak Suspected'),
                        ('CPU Instability Detected', 'CPU Instability Detected'),
                        ('Abnormal Thermal Rise',    'Abnormal Thermal Rise'),
                        ('Power Spike Detected',     'Power Spike Detected'),
                    ],
                    default='Normal',
                    max_length=50,
                )),
                ('cause',      models.CharField(blank=True, max_length=200, null=True)),
                ('confidence', models.FloatField(default=0.0)),
            ],
            options={'ordering': ['-timestamp']},
        ),
    ]
