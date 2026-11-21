from django.urls import path
from . import views

urlpatterns = [
    path('', views.bienvenida, name='bienvenida'),
    path('dispositivo/<str:modo>/', views.elegir_dispositivo, name='elegir_dispositivo'),
    path('ingresar/', views.pantalla_inicio, name='inicio'),
    path('registro/', views.registro, name='registro'),
    path('salir/', views.cerrar_sesion, name='cerrar_sesion'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('menu/', views.menu_principal, name='menu'),
    path('stock/', views.vista_stock, name='stock'),
    path('ventas/', views.vista_ventas, name='ventas'),
    path('ganancias/', views.ganancias, name='ganancias'),
    path('tendencias/', views.tendencias, name='tendencias'),
    path('perfil/', views.perfil, name='perfil'),
    path('crear-producto/', views.crear_producto, name='crear_producto'),
    path('editar-producto/<int:producto_id>/', views.editar_producto, name='editar_producto'),
    path('eliminar-producto/<int:producto_id>/', views.eliminar_producto, name='eliminar_producto'),
]
