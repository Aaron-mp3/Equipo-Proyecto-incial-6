
from django.db import models
from django.contrib.auth.models import User

class PerfilDueno(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre_pyme = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre_pyme

class Producto(models.Model):
    dueno = models.ForeignKey(PerfilDueno, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=150)
    cantidad_actual = models.IntegerField(default=0)
    precio_costo = models.IntegerField(help_text="Costo para valorizar inventario")
    precio_venta = models.IntegerField(help_text="Precio para calcular margen de ganancias")

    def __str__(self):
        return self.nombre