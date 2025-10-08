from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('patients/new/', views.patient_create, name='patient_create'),
    path('appointments/new/', views.appointment_create, name='appointment_create'),
    path('opd/<int:appointment_id>/print/', views.print_opd, name='print_opd'),
]
