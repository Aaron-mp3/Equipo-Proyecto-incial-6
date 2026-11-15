
# Register your models here.
from django.contrib import admin
from .models import PerfilDueno, Producto, PerfilPyme

admin.site.register(PerfilDueno)
admin.site.register(Producto)
admin.site.register(PerfilPyme)