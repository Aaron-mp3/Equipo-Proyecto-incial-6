from django.test import TestCase
from django.urls import reverse

from .models import PerfilPyme, Producto, Venta


def crear_pyme(correo='a@a.cl', contrasena='clave123', nombre='Pyme A'):
    pyme = PerfilPyme(nombre_pyme=nombre, correo=correo)
    pyme.set_password(contrasena)
    pyme.save()
    return pyme


class CuentaTests(TestCase):
    def test_registro_guarda_contrasena_con_hash(self):
        self.client.post(reverse('registro'), {
            'nombre_pyme': 'Mi Pyme', 'correo': 'x@x.cl', 'contrasena': 'secreta1',
        })
        pyme = PerfilPyme.objects.get(correo='x@x.cl')
        self.assertNotEqual(pyme.contrasena, 'secreta1')
        self.assertTrue(pyme.verificar_contrasena('secreta1'))

    def test_registro_rechaza_correo_repetido(self):
        crear_pyme(correo='x@x.cl')
        respuesta = self.client.post(reverse('registro'), {
            'nombre_pyme': 'Otra', 'correo': 'X@x.cl', 'contrasena': 'otra123',
        })
        self.assertContains(respuesta, 'Ya existe una cuenta')
        self.assertEqual(PerfilPyme.objects.count(), 1)

    def test_login_correcto_y_dashboard(self):
        crear_pyme()
        respuesta = self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.assertRedirects(respuesta, reverse('dashboard'))

    def test_login_incorrecto(self):
        crear_pyme()
        respuesta = self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'mala'})
        self.assertContains(respuesta, 'incorrectos')
        self.assertNotIn('pyme_id', self.client.session)

    def test_cuenta_antigua_con_contrasena_en_texto_plano_se_actualiza(self):
        PerfilPyme.objects.create(nombre_pyme='Vieja', correo='v@v.cl', contrasena='1234')
        self.client.post(reverse('inicio'), {'correo': 'v@v.cl', 'contrasena': '1234'})
        self.assertIn('pyme_id', self.client.session)
        self.assertNotEqual(PerfilPyme.objects.get(correo='v@v.cl').contrasena, '1234')

    def test_dashboard_muestra_resumen(self):
        pyme = crear_pyme()
        Producto.objects.create(dueno=pyme, nombre='A', cantidad_actual=10, precio_costo=1, precio_venta=2)
        Producto.objects.create(dueno=pyme, nombre='B', cantidad_actual=2, precio_costo=1, precio_venta=2)
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.context['total_productos'], 2)
        self.assertEqual(respuesta.context['total_unidades'], 12)
        self.assertEqual(respuesta.context['stock_bajo'], 1)
        self.assertContains(respuesta, 'Bienvenido, Pyme A')

    def test_paginas_privadas_piden_sesion(self):
        for nombre in ['dashboard', 'menu', 'stock', 'ventas', 'crear_producto']:
            respuesta = self.client.get(reverse(nombre))
            self.assertRedirects(respuesta, reverse('inicio'), msg_prefix=nombre)


class ProductosTests(TestCase):
    def setUp(self):
        self.pyme = crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})

    def test_crear_producto(self):
        self.client.post(reverse('crear_producto'), {
            'nombre': 'Café', 'cantidad': '20', 'precio_costo': '3000', 'precio_venta': '5000',
        })
        producto = Producto.objects.get()
        self.assertEqual((producto.dueno, producto.cantidad_actual, producto.precio_costo, producto.precio_venta),
                         (self.pyme, 20, 3000, 5000))

    def test_buscar_muestra_precio_y_cantidad(self):
        Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=20,
                                precio_costo=3000, precio_venta=5000)
        respuesta = self.client.get(reverse('menu'), {'q': 'caf'})
        self.assertContains(respuesta, '20 unidades')
        self.assertContains(respuesta, '$5000')

    def test_eliminar_producto(self):
        producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=1,
                                           precio_costo=1, precio_venta=2)
        self.client.post(reverse('eliminar_producto', args=[producto.id]))
        self.assertFalse(Producto.objects.exists())

    def test_no_se_puede_eliminar_producto_de_otra_pyme(self):
        otra = crear_pyme(correo='b@b.cl', nombre='Pyme B')
        ajeno = Producto.objects.create(dueno=otra, nombre='Ajeno', cantidad_actual=1,
                                        precio_costo=1, precio_venta=2)
        respuesta = self.client.post(reverse('eliminar_producto', args=[ajeno.id]))
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(Producto.objects.filter(id=ajeno.id).exists())

    def test_eliminar_exige_post(self):
        producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=1,
                                           precio_costo=1, precio_venta=2)
        respuesta = self.client.get(reverse('eliminar_producto', args=[producto.id]))
        self.assertEqual(respuesta.status_code, 405)
        self.assertTrue(Producto.objects.exists())


class VentasTests(TestCase):
    def setUp(self):
        self.pyme = crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=10,
                                                precio_costo=3000, precio_venta=5000)

    def vender(self, texto, cantidad):
        return self.client.post(reverse('ventas'), {'accion': 'confirmar', 'q': texto, 'cantidad': str(cantidad)})

    def test_venta_descuenta_stock_y_guarda_ganancia(self):
        self.vender('Café', 3)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad_actual, 7)
        venta = Venta.objects.get()
        self.assertEqual((venta.cantidad, venta.precio_unitario, venta.ganancia), (3, 5000, 6000))

    def test_ventas_persisten_y_se_muestran(self):
        self.vender('Café', 1)
        respuesta = self.client.get(reverse('ventas'))
        self.assertContains(respuesta, 'GANANCIAS: $2000')

    def test_stock_insuficiente(self):
        respuesta = self.vender('Café', 11)
        self.assertContains(respuesta, 'Stock insuficiente')
        self.assertFalse(Venta.objects.exists())

    def test_venta_sigue_en_historial_si_se_elimina_el_producto(self):
        self.vender('Café', 1)
        self.producto.delete()
        self.assertEqual(Venta.objects.get().nombre_producto, 'Café')
