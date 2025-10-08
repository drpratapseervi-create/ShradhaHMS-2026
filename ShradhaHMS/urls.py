# C:\ShradhaHMS_Full\ShradhaHMS_Full\ShradhaHMS\urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Your public site / dashboard
    path('', include('hms.urls')),

    # Billing module (PDF Final Bill, Advance Slip etc.)
    path('billing/', include(('billing.urls', 'billing'), namespace='billing')),

    # OPD prescription module
    path('opd/', include('opd.urls')),

    # If you are using the earlier OPS module (prescriptions/discharge), uncomment:
    # path('ops/', include(('ops.urls', 'ops'), namespace='ops')),
]

# Serve media (uploads) during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

