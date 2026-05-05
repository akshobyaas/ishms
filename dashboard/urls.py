from django.urls import path
from dashboard import views

urlpatterns = [
    path('',                 views.dashboard,       name='dashboard'),
    path('api/latest/',      views.api_latest,      name='api_latest'),
    path('api/anomalies/',   views.api_anomalies,   name='api_anomalies'),
    path('api/stats/',       views.api_stats,       name='api_stats'),
    path('api/history/',     views.api_history,     name='api_history'),
    path('api/export/',      views.api_export_csv,  name='api_export_csv'),
    path('api/manual-test/', views.api_manual_test, name='api_manual_test'),
    path('api/upload-csv/',  views.api_upload_csv,  name='api_upload_csv'),
]
