"""
Django management command to continuously collect telemetry and save to DB.

Usage:
    python manage.py collect_telemetry
    python manage.py collect_telemetry --interval 5
"""

import time
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Starts continuous telemetry collection and anomaly detection'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval', type=float, default=2.0,
            help='Seconds between readings (default: 2)',
        )

    def handle(self, *args, **options):
        from dashboard.core.data_collector import get_data
        from dashboard.models import TelemetryReading
        from dashboard.services.analysis_service import run_analyze

        interval = options['interval']
        self.stdout.write(self.style.SUCCESS(
            f'Telemetry collection started (interval={interval}s). Ctrl+C to stop.'
        ))

        try:
            while True:
                data = get_data()
                result = run_analyze(data)

                TelemetryReading.objects.create(
                    cpu=data['cpu'],
                    memory=data['memory'],
                    temperature=data['temperature'],
                    power=data['power'],
                    temp_source=data.get('temp_source', 'fallback'),
                    power_source=data.get('power_source', 'fallback'),
                    status=result.get('status', 'Normal'),
                    cause=result.get('cause') or '',
                    confidence=result.get('confidence', 0.0),
                )

                is_bad = result['status'] not in ('Normal', 'Suspicious')
                style = self.style.ERROR if is_bad else self.style.SUCCESS
                self.stdout.write(
                    f"CPU={data['cpu']:.1f}%  MEM={data['memory']:.1f}%  "
                    f"TEMP={data['temperature']:.1f}°C  PWR={data['power']:.1f}W  "
                    f"→ {style(result['status'])}"
                )

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nCollection stopped.'))
