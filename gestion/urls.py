from django.urls import path
from . import views

urlpatterns = [
    path('', views.pantalla_inicio, name='inicio'),
    path('registro/', views.registro, name='registro'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('menu/', views.menu_principal, name='menu'),
    path('stock/', views.vista_stock, name='stock'),
    path('ventas/', views.vista_ventas, name='ventas'), 
]