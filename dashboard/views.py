import csv
import io
import json
from datetime import datetime

from django.db.models import Avg, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from dashboard.models import ANOMALY_STATUSES, TelemetryReading
from dashboard.services.analysis_service import run_manual_test
from dashboard.services.monitoring_service import get_history

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

MANUAL_LIMITS = {
    'cpu':         (0, 100, 'CPU must be 0–100 %'),
    'memory':      (0, 100, 'Memory must be 0–100 %'),
    'temperature': (20, 120, 'Temperature must be 20–120 °C'),
    'power':       (10, 800, 'Power must be 10–800 W'),
}


def _int_param(request, name, default, lo, hi):
    """Read an integer query parameter, falling back to default and clamping."""
    try:
        value = int(request.GET.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(value, hi))


# ── Pages ──────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
def dashboard(request):
    return render(request, 'dashboard/index.html')


# ── Live data APIs ─────────────────────────────────────────────────────────────

@require_GET
def api_latest(request):
    limit = _int_param(request, 'limit', 30, 1, 500)
    readings = list(reversed(
        list(TelemetryReading.objects.order_by('-timestamp', '-id')[:limit])
    ))

    data = {
        'labels':          [r.timestamp.strftime('%H:%M:%S') for r in readings],
        'cpu':             [r.cpu for r in readings],
        'memory':          [r.memory for r in readings],
        'temperature':     [r.temperature for r in readings],
        'power':           [r.power for r in readings],
        'status':          [r.status for r in readings],
        'anomaly_indices': [i for i, r in enumerate(readings) if r.is_anomaly()],
    }

    if readings:
        latest = readings[-1]
        data['current'] = {
            'cpu':          round(latest.cpu, 1),
            'memory':       round(latest.memory, 1),
            'temperature':  round(latest.temperature, 1),
            'power':        round(latest.power, 1),
            'temp_source':  latest.temp_source,
            'power_source': latest.power_source,
            'status':       latest.status,
            'cause':        latest.cause or 'None',
            'confidence':   round(latest.confidence, 2),
            'timestamp':    latest.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_anomaly':   latest.is_anomaly(),
        }

    return JsonResponse(data)


@require_GET
def api_anomalies(request):
    anomalies = TelemetryReading.objects.filter(
        status__in=ANOMALY_STATUSES
    ).order_by('-timestamp', '-id')[:20]

    return JsonResponse({'anomalies': [{
        'timestamp':   r.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'cpu':         r.cpu,
        'memory':      r.memory,
        'temperature': r.temperature,
        'power':       r.power,
        'status':      r.status,
        'cause':       r.cause or 'Unknown',
        'confidence':  r.confidence,
    } for r in anomalies]})


@require_GET
def api_stats(request):
    total         = TelemetryReading.objects.count()
    anomaly_count = TelemetryReading.objects.filter(status__in=ANOMALY_STATUSES).count()
    stats         = TelemetryReading.objects.aggregate(
        avg_cpu=Avg('cpu'),   avg_memory=Avg('memory'),
        avg_temp=Avg('temperature'), avg_power=Avg('power'),
        max_cpu=Max('cpu'),   max_temp=Max('temperature'),
    )

    return JsonResponse({
        'total_readings': total,
        'anomaly_count':  anomaly_count,
        'anomaly_rate':   round((anomaly_count / total * 100) if total else 0, 1),
        **{k: round(v, 1) if v is not None else 0 for k, v in stats.items()},
    })


@require_GET
def api_history(request):
    result = get_history(
        status_filter=request.GET.get('status_filter', 'all'),
        search=request.GET.get('search', '').strip(),
        page=_int_param(request, 'page', 1, 1, 1_000_000),
        page_size=_int_param(request, 'page_size', 50, 1, 200),
    )
    return JsonResponse(result)


@require_GET
def api_export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="telemetry_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'timestamp', 'cpu', 'memory', 'temperature', 'power',
        'temp_source', 'power_source', 'status', 'cause', 'confidence',
    ])
    # Oldest first, so the export can be re-uploaded for offline analysis.
    for r in TelemetryReading.objects.order_by('timestamp', 'id').iterator():
        writer.writerow([
            r.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            r.cpu, r.memory, r.temperature, r.power,
            r.temp_source, r.power_source, r.status, r.cause, r.confidence,
        ])
    return response


# ── Analysis APIs ──────────────────────────────────────────────────────────────

@require_POST
def api_manual_test(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Request body must be JSON'}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({'error': 'Request body must be a JSON object'}, status=400)

    values = {}
    for field, (lo, hi, message) in MANUAL_LIMITS.items():
        try:
            value = float(body[field])
        except (KeyError, TypeError, ValueError):
            return JsonResponse({'error': 'Invalid input — all fields must be numbers'}, status=400)
        if not lo <= value <= hi:
            return JsonResponse({'error': message}, status=400)
        values[field] = value

    try:
        result = run_manual_test(**values)
    except Exception as e:
        return JsonResponse({'error': f'Analysis failed: {e}'}, status=500)
    return JsonResponse({'result': result})


@require_POST
def api_upload_csv(request):
    upload = request.FILES.get('file')
    if upload is None:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    if upload.size > MAX_UPLOAD_BYTES:
        return JsonResponse({'error': 'File too large — limit is 5 MB'}, status=400)

    from dashboard.core.offline_analyzer import analyze_csv

    try:
        result = analyze_csv(io.BytesIO(upload.read()))
    except Exception as e:
        return JsonResponse({'error': f'Analysis failed: {e}'}, status=500)
    if 'error' in result:
        return JsonResponse({'error': result['error']}, status=400)
    return JsonResponse(result)
