from django.urls import path
from . import views

urlpatterns = [
    path('', views.pantalla_inicio, name='inicio'),
    path('menu/', views.menu_principal, name='menu'),
    path('registro/', views.registro, name='registro'),
    path('dashboard/', views.dashboard, name='dashboard'),
]