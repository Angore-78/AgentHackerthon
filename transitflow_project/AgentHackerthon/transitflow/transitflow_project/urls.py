from django.contrib import admin
from django.urls import path, include
from core.views import portal_redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', portal_redirect, name='home'),
    path('auth/', include('core.urls')),
    path('', include('logistics.urls')),
    path('payments/', include('payments.urls')),
    path('assistant/', include('assistant.urls')),
]
