from dashboard.models import TelemetryReading


def get_history(status_filter="all", search="", page=1, page_size=50):
    """
    Return a paginated, filterable list of telemetry readings from the DB.
    Called by the /api/history/ endpoint.
    """
    qs = TelemetryReading.objects.order_by('-timestamp', '-id')

    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)

    if search:
        qs = qs.filter(cause__icontains=search)

    total = qs.count()
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))

    offset = (page - 1) * page_size
    records = qs[offset: offset + page_size]

    return {
        "records": [
            {
                "timestamp":   r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "cpu":         r.cpu,
                "memory":      r.memory,
                "temperature": r.temperature,
                "power":       r.power,
                "temp_source": r.temp_source,
                "power_source": r.power_source,
                "status":      r.status,
                "cause":       r.cause or "",
                "confidence":  r.confidence,
            }
            for r in records
        ],
        "total":        total,
        "pages":        pages,
        "current_page": page,
        "page_size":    page_size,
    }
