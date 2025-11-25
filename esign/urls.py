"""
URL configuration for esign project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health.health_check, name='health'),
    path('health/detailed/', health.health_detailed, name='health-detailed'),
    path('api/auth/', include('users.urls')),
    path('api/documents/', include('documents.urls')),
    path('api/envelopes/', include('envelopes.urls')),
    path('api/signatures/', include('signatures.urls')),
    path('api/fields/', include('fields.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/audit/', include('audit.urls')),
    path('api/contacts/', include('contacts.urls')),
]

# Serve media files during development only
# In production, use a web server or S3 for serving media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
