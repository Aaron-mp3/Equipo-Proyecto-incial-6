import shutil
import tempfile
from datetime import timedelta
from unittest import skipUnless

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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
        for nombre in ['dashboard', 'menu', 'stock', 'ventas', 'crear_producto', 'ganancias', 'tendencias', 'perfil']:
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

    def test_editar_suma_unidades_y_cambia_precios(self):
        producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=10,
                                           precio_costo=3000, precio_venta=5000)
        respuesta = self.client.post(reverse('editar_producto', args=[producto.id]), {
            'nombre': 'Café molido', 'agregar': '15', 'precio_costo': '3500', 'precio_venta': '6000', 'volver': 'stock',
        })
        self.assertRedirects(respuesta, reverse('stock'))
        producto.refresh_from_db()
        self.assertEqual((producto.nombre, producto.cantidad_actual, producto.precio_costo, producto.precio_venta),
                         ('Café molido', 25, 3500, 6000))

    def test_editar_con_cero_unidades_no_cambia_el_stock(self):
        producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=10,
                                           precio_costo=3000, precio_venta=5000)
        self.client.post(reverse('editar_producto', args=[producto.id]), {
            'nombre': 'Café', 'agregar': '', 'precio_costo': '3000', 'precio_venta': '5500',
        })
        producto.refresh_from_db()
        self.assertEqual((producto.cantidad_actual, producto.precio_venta), (10, 5500))

    def test_editar_rechaza_valores_negativos_y_nombre_repetido(self):
        a = Producto.objects.create(dueno=self.pyme, nombre='A', cantidad_actual=1, precio_costo=1, precio_venta=2)
        Producto.objects.create(dueno=self.pyme, nombre='B', cantidad_actual=1, precio_costo=1, precio_venta=2)
        url = reverse('editar_producto', args=[a.id])
        r1 = self.client.post(url, {'nombre': 'A', 'agregar': '-3', 'precio_costo': '1', 'precio_venta': '2'})
        self.assertContains(r1, 'no pueden ser negativos')
        r2 = self.client.post(url, {'nombre': 'b', 'agregar': '0', 'precio_costo': '1', 'precio_venta': '2'})
        self.assertContains(r2, 'Ya tienes otro producto')
        a.refresh_from_db()
        self.assertEqual((a.nombre, a.cantidad_actual), ('A', 1))

    def test_no_se_puede_editar_producto_de_otra_pyme(self):
        otra = crear_pyme(correo='b@b.cl', nombre='Pyme B')
        ajeno = Producto.objects.create(dueno=otra, nombre='Ajeno', cantidad_actual=1, precio_costo=1, precio_venta=2)
        respuesta = self.client.post(reverse('editar_producto', args=[ajeno.id]), {
            'nombre': 'Robado', 'agregar': '99', 'precio_costo': '1', 'precio_venta': '2',
        })
        self.assertEqual(respuesta.status_code, 404)
        ajeno.refresh_from_db()
        self.assertEqual((ajeno.nombre, ajeno.cantidad_actual), ('Ajeno', 1))

    def test_stock_marca_stock_bajo_desde_5_unidades(self):
        Producto.objects.create(dueno=self.pyme, nombre='Poco', cantidad_actual=5, precio_costo=1, precio_venta=2)
        Producto.objects.create(dueno=self.pyme, nombre='Harto', cantidad_actual=6, precio_costo=1, precio_venta=2)
        respuesta = self.client.get(reverse('stock'))
        self.assertContains(respuesta, 'Stock bajo', count=2)  # 1 insignia + 1 texto de la leyenda
        self.assertContains(respuesta, 'Stock normal', count=1)

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


class GananciasPorDiaTests(TestCase):
    def setUp(self):
        self.pyme = crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.producto = Producto.objects.create(dueno=self.pyme, nombre='Café', cantidad_actual=50,
                                                precio_costo=3000, precio_venta=5000)

    def vender(self, cantidad, fecha=''):
        return self.client.post(reverse('ventas'), {
            'accion': 'confirmar', 'q': 'Café', 'cantidad': str(cantidad), 'fecha': fecha,
        })

    def test_calendario_muestra_las_ganancias_de_hoy(self):
        self.vender(2)  # (5000 - 3000) x 2
        respuesta = self.client.get(reverse('ganancias'))
        self.assertEqual(respuesta.context['resumen']['ganancia_txt'], '$4000')
        self.assertEqual(respuesta.context['detalle']['ganancia_txt'], '$4000')
        self.assertEqual(len(respuesta.context['detalle']['filas']), 1)

    def test_venta_con_fecha_de_un_dia_anterior(self):
        ayer = timezone.localdate() - timedelta(days=1)
        self.vender(1, fecha=ayer.isoformat())
        venta = Venta.objects.get()
        self.assertEqual(timezone.localtime(venta.fecha).date(), ayer)
        respuesta = self.client.get(reverse('ganancias'), {
            'mes': f"{ayer.year}-{ayer.month:02d}", 'dia': ayer.isoformat(),
        })
        self.assertEqual(respuesta.context['detalle']['ganancia_txt'], '$2000')

    def test_fecha_futura_se_rechaza(self):
        manana = timezone.localdate() + timedelta(days=1)
        respuesta = self.vender(1, fecha=manana.isoformat())
        self.assertContains(respuesta, 'no puede ser futura')
        self.assertFalse(Venta.objects.exists())

    def test_fecha_invalida_se_rechaza(self):
        respuesta = self.vender(1, fecha='no-es-fecha')
        self.assertContains(respuesta, 'no es válida')
        self.assertFalse(Venta.objects.exists())

    def test_calendario_ignora_parametros_raros(self):
        for params in ({'mes': 'basura'}, {'mes': '2999-01'}, {'dia': 'x'}, {'mes': '2026-13'}):
            self.assertEqual(self.client.get(reverse('ganancias'), params).status_code, 200, params)

    def test_ventas_de_otra_pyme_no_aparecen(self):
        otra = crear_pyme(correo='b@b.cl', nombre='Pyme B')
        ajeno = Producto.objects.create(dueno=otra, nombre='X', cantidad_actual=5, precio_costo=1, precio_venta=100)
        Venta.objects.create(pyme=otra, producto=ajeno, nombre_producto='X', cantidad=1, precio_unitario=100, ganancia=99)
        respuesta = self.client.get(reverse('ganancias'))
        self.assertEqual(respuesta.context['resumen']['ventas'], 0)

    def test_tendencias_sube_si_hoy_hay_ventas_y_ayer_no(self):
        self.vender(1)
        respuesta = self.client.get(reverse('tendencias'))
        dia = respuesta.context['periodos'][0]
        self.assertEqual((dia['tendencia'], dia['porcentaje']), ('sube', None))
        self.assertEqual(len(respuesta.context['serie']['barras']), 30)

    def test_tendencias_baja_si_ayer_vendio_mas(self):
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.vender(4, fecha=ayer)   # 8000 ayer
        self.vender(1)               # 2000 hoy
        dia = self.client.get(reverse('tendencias')).context['periodos'][0]
        self.assertEqual((dia['tendencia'], dia['porcentaje']), ('baja', 75))

    def test_tendencias_metrica_invalida_usa_ganancias(self):
        respuesta = self.client.get(reverse('tendencias'), {'m': 'cualquiera'})
        self.assertEqual(respuesta.context['metrica'], 'ganancia')


class PerfilTests(TestCase):
    def setUp(self):
        self.pyme = crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})

    def datos(self, **cambios):
        base = {'accion': 'datos', 'nombre_pyme': 'Pyme A', 'correo': 'a@a.cl', 'contrasena_actual': ''}
        base.update(cambios)
        return self.client.post(reverse('perfil'), base)

    def test_cambiar_nombre_no_pide_contrasena(self):
        self.datos(nombre_pyme='Nuevo Nombre')
        self.pyme.refresh_from_db()
        self.assertEqual(self.pyme.nombre_pyme, 'Nuevo Nombre')

    def test_cambiar_correo_exige_contrasena_actual(self):
        respuesta = self.datos(correo='nuevo@a.cl')
        self.assertContains(respuesta, 'contraseña actual')
        self.pyme.refresh_from_db()
        self.assertEqual(self.pyme.correo, 'a@a.cl')

        self.datos(correo='Nuevo@A.cl', contrasena_actual='clave123')
        self.pyme.refresh_from_db()
        self.assertEqual(self.pyme.correo, 'nuevo@a.cl')

    def test_no_se_puede_usar_el_correo_de_otra_cuenta(self):
        crear_pyme(correo='b@b.cl', nombre='Pyme B')
        respuesta = self.datos(correo='B@b.cl', contrasena_actual='clave123')
        self.assertContains(respuesta, 'Ya existe otra cuenta')

    def test_correo_invalido(self):
        respuesta = self.datos(correo='esto-no-es-un-correo', contrasena_actual='clave123')
        self.assertContains(respuesta, 'correo válido')

    def cambiar_contrasena(self, actual='clave123', nueva='Nueva-clave-2026', repetida=None):
        return self.client.post(reverse('perfil'), {
            'accion': 'contrasena', 'contrasena_actual': actual, 'contrasena_nueva': nueva,
            'contrasena_repetida': nueva if repetida is None else repetida,
        })

    def test_cambiar_contrasena_ok_y_cierra_otras_sesiones(self):
        otro_dispositivo = Client()
        otro_dispositivo.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.assertEqual(otro_dispositivo.get(reverse('dashboard')).status_code, 200)

        self.cambiar_contrasena()
        self.pyme.refresh_from_db()
        self.assertTrue(self.pyme.verificar_contrasena('Nueva-clave-2026'))
        self.assertNotEqual(self.pyme.contrasena, 'Nueva-clave-2026')

        # la sesión desde donde se cambió sigue activa; la otra se cerró
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertRedirects(otro_dispositivo.get(reverse('dashboard')), reverse('inicio'))

    def test_contrasena_actual_incorrecta(self):
        respuesta = self.cambiar_contrasena(actual='mala')
        self.assertContains(respuesta, 'actual no es correcta')
        self.pyme.refresh_from_db()
        self.assertTrue(self.pyme.verificar_contrasena('clave123'))

    def test_nueva_contrasena_no_coincide_o_es_igual(self):
        self.assertContains(self.cambiar_contrasena(repetida='otra-distinta'), 'no coinciden')
        self.assertContains(self.cambiar_contrasena(nueva='clave123'), 'distinta de la actual')

    @skipUnless(settings.AUTH_PASSWORD_VALIDATORS, 'el proyecto no define validadores de contraseña')
    def test_contrasena_debil_se_rechaza(self):
        respuesta = self.cambiar_contrasena(nueva='abc')
        self.assertEqual(respuesta.status_code, 200)
        self.pyme.refresh_from_db()
        self.assertTrue(self.pyme.verificar_contrasena('clave123'))

    def test_foto_de_perfil_subir_y_quitar(self):
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=carpeta):
            png = SimpleUploadedFile('mi foto.png', b'\x89PNG\r\n\x1a\n' + b'0' * 64, content_type='image/png')
            self.client.post(reverse('perfil'), {'accion': 'foto', 'foto': png})
            self.pyme.refresh_from_db()
            self.assertTrue(self.pyme.foto.name.startswith('perfiles/'))
            self.assertTrue(self.pyme.foto.name.endswith('.png'))
            self.assertNotIn(' ', self.pyme.foto.name)   # el nombre original no se conserva

            self.client.post(reverse('perfil'), {'accion': 'quitar_foto'})
            self.pyme.refresh_from_db()
            self.assertFalse(self.pyme.foto)

    def test_foto_que_no_es_imagen_se_rechaza(self):
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=carpeta):
            falsa = SimpleUploadedFile('virus.png', b'<script>alert(1)</script>', content_type='image/png')
            respuesta = self.client.post(reverse('perfil'), {'accion': 'foto', 'foto': falsa})
            self.assertContains(respuesta, 'debe ser una imagen')
            self.pyme.refresh_from_db()
            self.assertFalse(self.pyme.foto)

    def test_foto_muy_pesada_se_rechaza(self):
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        with override_settings(MEDIA_ROOT=carpeta):
            grande = SimpleUploadedFile('grande.png', b'\x89PNG\r\n\x1a\n' + b'0' * (2 * 1024 * 1024 + 1))
            respuesta = self.client.post(reverse('perfil'), {'accion': 'foto', 'foto': grande})
            self.assertContains(respuesta, '2 MB')


class DispositivoTests(TestCase):
    CELULAR = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
    PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'

    def test_detecta_celular_y_computador(self):
        self.assertEqual(self.client.get(reverse('bienvenida'), HTTP_USER_AGENT=self.CELULAR).context['detectado'], 'celular')
        self.assertEqual(self.client.get(reverse('bienvenida'), HTTP_USER_AGENT=self.PC).context['detectado'], 'computador')

    def test_pantalla_muestra_los_dos_botones(self):
        respuesta = self.client.get(reverse('bienvenida'), HTTP_USER_AGENT=self.PC)
        self.assertContains(respuesta, 'Celular')
        self.assertContains(respuesta, 'Computador')
        self.assertContains(respuesta, 'Detectado', count=1)

    def test_elegir_dispositivo_guarda_cookie_y_va_al_login(self):
        respuesta = self.client.get(reverse('elegir_dispositivo', args=['celular']))
        self.assertRedirects(respuesta, reverse('inicio'))
        self.assertEqual(respuesta.cookies['dispositivo'].value, 'celular')

    def test_dispositivo_invalido(self):
        self.assertEqual(self.client.get(reverse('elegir_dispositivo', args=['tostadora'])).status_code, 404)

    def test_modo_celular_se_aplica_al_diseno(self):
        crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.client.cookies['dispositivo'] = 'celular'
        self.assertContains(self.client.get(reverse('dashboard')), 'modo-celular')
        self.client.cookies['dispositivo'] = 'computador'
        self.assertContains(self.client.get(reverse('dashboard')), 'modo-computador')

    def test_con_sesion_iniciada_la_bienvenida_lleva_al_dashboard(self):
        crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.assertRedirects(self.client.get(reverse('bienvenida')), reverse('dashboard'))

    def test_cerrar_sesion_vuelve_a_la_bienvenida(self):
        crear_pyme()
        self.client.post(reverse('inicio'), {'correo': 'a@a.cl', 'contrasena': 'clave123'})
        self.assertRedirects(self.client.post(reverse('cerrar_sesion')), reverse('bienvenida'))
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('inicio'))
