from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare


class PerfilPyme(models.Model):
    """Cuenta de una PYME. Es la única "dueña" de productos y ventas."""

    nombre_pyme = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    contrasena = models.CharField(max_length=128)
    foto = models.FileField(upload_to='perfiles/', blank=True)

    def __str__(self):
        return self.nombre_pyme

    def set_password(self, contrasena_plana):
        """Guarda la contraseña con hash (nunca en texto plano)."""
        self.contrasena = make_password(contrasena_plana)

    def _tiene_hash(self):
        try:
            identify_hasher(self.contrasena)
            return True
        except ValueError:
            return False

    def verificar_contrasena(self, contrasena_plana):
        if self._tiene_hash():
            return check_password(contrasena_plana, self.contrasena)

        # Cuenta antigua con la contraseña en texto plano: si coincide,
        # se acepta y se guarda de inmediato con hash.
        if constant_time_compare(contrasena_plana, self.contrasena):
            self.set_password(contrasena_plana)
            self.save(update_fields=['contrasena'])
            return True
        return False


class Producto(models.Model):
    dueno = models.ForeignKey(PerfilPyme, on_delete=models.CASCADE, related_name='productos')
    nombre = models.CharField(max_length=150)
    cantidad_actual = models.IntegerField(default=0)
    precio_costo = models.IntegerField(help_text="Precio de compra: costo para valorizar inventario")
    precio_venta = models.IntegerField(help_text="Precio al que se vende al público")

    def __str__(self):
        return self.nombre


class Venta(models.Model):
    pyme = models.ForeignKey(PerfilPyme, on_delete=models.CASCADE, related_name='ventas')
    # Si se elimina el producto, la venta queda en el historial.
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True)
    nombre_producto = models.CharField(max_length=150)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.IntegerField()
    ganancia = models.IntegerField(help_text="(precio de venta - precio de costo) x cantidad")
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"{self.cantidad} x {self.nombre_producto}"
