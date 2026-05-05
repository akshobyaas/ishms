import csv
import json
from datetime import datetime

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from dashboard.models import TelemetryReading
from dashboard.services.monitoring_service import get_history
from dashboard.services.analysis_service import run_manual_test

ANOMALY_STATUSES = {
    "Confirmed Anomaly",
    "Memory Leak Suspected",
    "CPU Instability Detected",
    "Abnormal Thermal Rise",
    "Power Spike Detected",
}


# ── Pages ──────────────────────────────────────────────────────────────────────

def dashboard(request):
    return render(request, 'dashboard/index.html')


# ── Live data APIs ─────────────────────────────────────────────────────────────

@require_GET
def api_latest(request):
    limit = int(request.GET.get('limit', 30))
    readings = list(reversed(
        list(TelemetryReading.objects.order_by('-timestamp')[:limit])
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
            'cpu':         round(latest.cpu, 1),
            'memory':      round(latest.memory, 1),
            'temperature': round(latest.temperature, 1),
            'power':       round(latest.power, 1),
            'status':      latest.status,
            'cause':       latest.cause or 'None',
            'confidence':  round(latest.confidence, 2),
            'timestamp':   latest.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_anomaly':  latest.is_anomaly(),
        }

    return JsonResponse(data)


@require_GET
def api_anomalies(request):
    anomalies = TelemetryReading.objects.filter(
        status__in=ANOMALY_STATUSES
    ).order_by('-timestamp')[:20]

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
    from django.db.models import Avg, Max

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
        **{k: round(v, 1) if v else 0 for k, v in stats.items()},
    })


@require_GET
def api_history(request):
    result = get_history(
        status_filter=request.GET.get('status_filter', 'all'),
        search=request.GET.get('search', '').strip(),
        page=int(request.GET.get('page', 1)),
        page_size=int(request.GET.get('page_size', 50)),
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
    for r in TelemetryReading.objects.order_by('-timestamp').iterator():
        writer.writerow([
            r.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            r.cpu, r.memory, r.temperature, r.power,
            r.temp_source, r.power_source, r.status, r.cause, r.confidence,
        ])
    return response


@csrf_exempt
@require_POST
def api_manual_test(request):
    try:
        body        = json.loads(request.body)
        cpu         = float(body['cpu'])
        memory      = float(body['memory'])
        temperature = float(body['temperature'])
        power       = float(body['power'])

        assert 0  <= cpu         <= 100, "CPU must be 0–100"
        assert 0  <= memory      <= 100, "Memory must be 0–100"
        assert 20 <= temperature <= 120, "Temperature must be 20–120 °C"
        assert 10 <= power       <= 800, "Power must be 10–800 W"

    except (KeyError, ValueError):
        return JsonResponse({'error': 'Invalid input — all fields must be numbers'}, status=400)
    except AssertionError as e:
        return JsonResponse({'error': str(e)}, status=400)

    try:
        result = run_manual_test(cpu, memory, temperature, power)
        return JsonResponse({'result': result})
    except Exception as e:
        return JsonResponse({'error': f'Analysis failed: {str(e)}'}, status=500)


@csrf_exempt
@require_POST
def api_upload_csv(request):
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)

    try:
        import io
        from dashboard.core.offline_analyzer import analyze_csv

        result = analyze_csv(io.BytesIO(request.FILES['file'].read()))
        if 'error' in result:
            return JsonResponse({'error': result['error']}, status=400)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
