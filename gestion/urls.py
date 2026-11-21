from django.urls import path
from . import views

urlpatterns = [
    path('', views.pantalla_inicio, name='inicio'),
    path('registro/', views.registro, name='registro'),
    path('salir/', views.cerrar_sesion, name='cerrar_sesion'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('menu/', views.menu_principal, name='menu'),
    path('stock/', views.vista_stock, name='stock'),
    path('ventas/', views.vista_ventas, name='ventas'),
    path('crear-producto/', views.crear_producto, name='crear_producto'),
    path('eliminar-producto/<int:producto_id>/', views.eliminar_producto, name='eliminar_producto'),
]
