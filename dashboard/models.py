from django.db import models


class TelemetryReading(models.Model):
    STATUS_CHOICES = [
        ('Normal',                   'Normal'),
        ('Suspicious',               'Suspicious'),
        ('Confirmed Anomaly',        'Confirmed Anomaly'),
        ('Memory Leak Suspected',    'Memory Leak Suspected'),
        ('CPU Instability Detected', 'CPU Instability Detected'),
        ('Abnormal Thermal Rise',    'Abnormal Thermal Rise'),
        ('Power Spike Detected',     'Power Spike Detected'),
    ]

    timestamp    = models.DateTimeField(auto_now_add=True)
    cpu          = models.FloatField()
    memory       = models.FloatField()
    temperature  = models.FloatField()
    power        = models.FloatField()
    temp_source  = models.CharField(max_length=20, default='fallback')
    power_source = models.CharField(max_length=20, default='fallback')
    status       = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Normal')
    cause        = models.CharField(max_length=200, blank=True, null=True)
    confidence   = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] CPU={self.cpu:.1f}% | {self.status}"

    def is_anomaly(self):
        return self.status not in ('Normal', 'Suspicious')
