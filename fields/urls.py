"""
URL configuration for fields app.
"""

from django.urls import path
from . import views

app_name = 'fields'

urlpatterns = [
    path('<uuid:envelope_id>/', views.EnvelopeFieldsView.as_view(), name='envelope_fields'),
    path('signing/<uuid:envelope_id>/', views.SigningFieldsListView.as_view(), name='signing_fields_list'),
    path('signing/<uuid:envelope_id>/values/', views.SigningFieldsValueSaveView.as_view(), name='signing_fields_values'),
]


