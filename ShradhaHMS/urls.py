"""
ShradhaHMS URL Configuration
---------------------------------
Main routing file for Shradha Hospital Management System.
Includes routes for the admin panel, HMS module (dashboard/public site),
and OPD module. The old Billing module has been completely removed.
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin panel
    path('admin/', admin.site.urls),

    # AUTH
    path('login/',  auth_views.LoginView.as_view(template_name='hms/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # Hospital Management System (main/public site)
    path('', include('hms.urls')),

    # Outpatient Department (OPD) module
    path('opd/', include('opd.urls')),
]

# ✅ Serve uploaded media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)