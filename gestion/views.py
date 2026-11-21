import calendar
import uuid
from datetime import date, datetime, time, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.http import require_POST

from . import estadisticas as est
from .models import PerfilPyme, Producto, Venta

# Un producto se marca como "stock bajo" cuando le quedan estas unidades o menos.
UMBRAL_STOCK_BAJO = 5

MAX_FOTO_BYTES = 2 * 1024 * 1024  # 2 MB


# ------------------------------------------------------------- sesión

def _sello(pyme):
    """Huella de la contraseña actual. Si la contraseña cambia, las sesiones
    abiertas con la anterior dejan de ser válidas."""
    return salted_hmac('gestion.sesion', pyme.contrasena).hexdigest()


def _iniciar_sesion(request, pyme):
    request.session.cycle_key()
    request.session['pyme_id'] = pyme.id
    request.session['nombre_pyme'] = pyme.nombre_pyme
    request.session['sello'] = _sello(pyme)


def _pyme_de_sesion(request):
    pyme = PerfilPyme.objects.filter(id=request.session.get('pyme_id')).first()
    if pyme and constant_time_compare(request.session.get('sello', ''), _sello(pyme)):
        return pyme
    return None


def pyme_requerida(vista):
    """Solo deja pasar si hay una PYME con sesión iniciada.

    Deja la PYME disponible como request.pyme.
    """
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        pyme = _pyme_de_sesion(request)
        if pyme is None:
            request.session.flush()
            return redirect('inicio')
        request.pyme = pyme
        return vista(request, *args, **kwargs)
    return envoltura


# ------------------------------------------------- dispositivo (antes del login)

def _detectar_dispositivo(request):
    agente = request.META.get('HTTP_USER_AGENT', '').lower()
    if any(clave in agente for clave in ('mobile', 'android', 'iphone', 'ipod')):
        return 'celular'
    return 'computador'


def bienvenida(request):
    if _pyme_de_sesion(request):
        return redirect('dashboard')
    return render(request, 'gestion/bienvenida.html', {
        'detectado': _detectar_dispositivo(request),
        'elegido': request.COOKIES.get('dispositivo', ''),
    })


def elegir_dispositivo(request, modo):
    if modo not in ('celular', 'computador'):
        raise Http404
    respuesta = redirect('inicio')
    respuesta.set_cookie('dispositivo', modo, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return respuesta


# ---------------------------------------------------------------- cuenta

def pantalla_inicio(request):
    mensaje_error = ""

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip()
        contrasena = request.POST.get('contrasena', '')

        pyme = PerfilPyme.objects.filter(correo__iexact=correo).first()

        if pyme and pyme.verificar_contrasena(contrasena):
            _iniciar_sesion(request, pyme)
            return redirect('dashboard')

        mensaje_error = "Correo o contraseña incorrectos."

    return render(request, 'gestion/login.html', {
        'mensaje_error': mensaje_error,
        'correo': request.POST.get('correo', ''),
    })


def registro(request):
    mensaje_error = ""

    if request.method == 'POST':
        nombre_pyme = request.POST.get('nombre_pyme', '').strip()
        correo = request.POST.get('correo', '').strip().lower()
        contrasena = request.POST.get('contrasena', '')

        if not nombre_pyme or not correo or not contrasena:
            mensaje_error = "Completa todos los campos."
        elif PerfilPyme.objects.filter(correo__iexact=correo).exists():
            mensaje_error = "Ya existe una cuenta con ese correo."
        else:
            pyme = PerfilPyme(nombre_pyme=nombre_pyme, correo=correo)
            pyme.set_password(contrasena)
            try:
                pyme.save()
            except IntegrityError:
                mensaje_error = "Ya existe una cuenta con ese correo."
            else:
                return redirect('inicio')

    return render(request, 'gestion/registro.html', {
        'mensaje_error': mensaje_error,
        'nombre_pyme': request.POST.get('nombre_pyme', ''),
        'correo': request.POST.get('correo', ''),
    })


@require_POST
def cerrar_sesion(request):
    request.session.flush()
    return redirect('bienvenida')


# ------------------------------------------------------------ ventas por día

def _rango_local(desde, hasta):
    """(inicio, fin) aware que cubren los días desde..hasta en la zona horaria de la app."""
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), zona)
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min), zona)
    return inicio, fin


def _ventas_por_dia(pyme, desde, hasta):
    inicio, fin = _rango_local(desde, hasta)
    filas = Venta.objects.filter(pyme=pyme, fecha__gte=inicio, fecha__lt=fin) \
                         .values_list('fecha', 'cantidad', 'precio_unitario', 'ganancia')
    return est.agrupar_por_dia(
        (timezone.localtime(fecha).date(), cantidad, precio, ganancia)
        for fecha, cantidad, precio, ganancia in filas
    )


@pyme_requerida
def dashboard(request):
    productos = Producto.objects.filter(dueno=request.pyme)
    resumen = productos.aggregate(total=Count('id'), unidades=Sum('cantidad_actual'))
    ganancias_totales = Venta.objects.filter(pyme=request.pyme).aggregate(total=Sum('ganancia'))['total'] or 0

    hoy = timezone.localdate()
    por_dia = _ventas_por_dia(request.pyme, hoy - timedelta(days=13), hoy)
    ganancia_hoy = por_dia.get(hoy, est.VACIO)['ganancia']
    semana = est.comparar_periodos(por_dia, hoy, 7, 'ganancia', 'la semana anterior')

    return render(request, 'gestion/dashboard.html', {
        'pyme': request.pyme,
        'total_productos': resumen['total'],
        'total_unidades': resumen['unidades'] or 0,
        'stock_bajo': productos.filter(cantidad_actual__lte=UMBRAL_STOCK_BAJO).count(),
        'ganancias': ganancias_totales,
        'ganancia_hoy_txt': est.moneda(ganancia_hoy),
        'tendencia_semana': semana,
        'umbral': UMBRAL_STOCK_BAJO,
    })


@pyme_requerida
def ganancias(request):
    hoy = timezone.localdate()
    anio, mes = est.parsear_mes(request.GET.get('mes'), hoy)
    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
    por_dia = _ventas_por_dia(request.pyme, primero, ultimo)

    seleccionado = est.parsear_dia(request.GET.get('dia'))
    if seleccionado is None or (seleccionado.year, seleccionado.month) != (anio, mes) or seleccionado > hoy:
        seleccionado = hoy if (hoy.year, hoy.month) == (anio, mes) else None

    detalle = None
    if seleccionado:
        inicio, fin = _rango_local(seleccionado, seleccionado)
        ventas = Venta.objects.filter(pyme=request.pyme, fecha__gte=inicio, fecha__lt=fin).order_by('fecha', 'id')
        datos = por_dia.get(seleccionado, est.VACIO)
        detalle = {
            'titulo': est.fecha_larga(seleccionado),
            'ganancia_txt': est.moneda(datos['ganancia']),
            'ingresos_txt': est.moneda(datos['ingresos']),
            'unidades': datos['unidades'],
            'filas': [{
                'hora': timezone.localtime(v.fecha).strftime('%H:%M'),
                'producto': v.nombre_producto,
                'cantidad': v.cantidad,
                'precio_txt': est.moneda(v.precio_unitario),
                'ganancia_txt': est.moneda(v.ganancia),
                'negativa': v.ganancia < 0,
            } for v in ventas],
        }

    anterior = est.mes_vecino(anio, mes, -1)
    siguiente = est.mes_vecino(anio, mes, 1)
    if siguiente > (hoy.year, hoy.month):
        siguiente = None

    return render(request, 'gestion/ganancias.html', {
        'titulo_mes': f"{est.NOMBRES_MESES[mes - 1].capitalize()} {anio}",
        'mes_txt': est.texto_mes(anio, mes),
        'anterior_txt': est.texto_mes(*anterior),
        'siguiente_txt': est.texto_mes(*siguiente) if siguiente else '',
        'dias_semana': ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'),
        'semanas': est.construir_calendario(por_dia, anio, mes, hoy, seleccionado),
        'resumen': est.resumen_mes(por_dia, anio, mes),
        'detalle': detalle,
    })


@pyme_requerida
def tendencias(request):
    hoy = timezone.localdate()
    metrica = request.GET.get('m')
    if metrica not in est.METRICAS:
        metrica = 'ganancia'

    por_dia = _ventas_por_dia(request.pyme, hoy - timedelta(days=59), hoy)
    periodos = [
        dict(titulo='Último día', subtitulo='Hoy comparado con ayer',
             etiquetas=('Ayer', 'Hoy'),
             **est.comparar_periodos(por_dia, hoy, 1, metrica, 'ayer')),
        dict(titulo='Última semana', subtitulo='Últimos 7 días comparados con los 7 anteriores',
             etiquetas=('7 días antes', 'Últimos 7 días'),
             **est.comparar_periodos(por_dia, hoy, 7, metrica, 'la semana anterior')),
        dict(titulo='Último mes', subtitulo='Últimos 30 días comparados con los 30 anteriores',
             etiquetas=('30 días antes', 'Últimos 30 días'),
             **est.comparar_periodos(por_dia, hoy, 30, metrica, 'el mes anterior')),
    ]

    return render(request, 'gestion/tendencias.html', {
        'metrica': metrica,
        'metricas': [(clave, datos[1]) for clave, datos in est.METRICAS.items()],
        'etiqueta_metrica': est.METRICAS[metrica][1],
        'periodos': periodos,
        'serie': est.serie_diaria(por_dia, hoy, 30, metrica),
    })


# ------------------------------------------------------------- productos

@pyme_requerida
def menu_principal(request):
    query = request.GET.get('q', '').strip()
    mensaje_error = ""

    productos = Producto.objects.filter(dueno=request.pyme).order_by('nombre')
    if query:
        productos = productos.filter(nombre__icontains=query)
    productos = list(productos)

    if query and not productos:
        mensaje_error = f"No se encontró el producto '{query}' en el inventario."

    return render(request, 'gestion/menu_principal.html', {
        'query': query,
        'resultados': productos,
        'mensaje_error': mensaje_error,
        'umbral': UMBRAL_STOCK_BAJO,
    })


@pyme_requerida
def crear_producto(request):
    mensaje_error = ""

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()

        try:
            cantidad = int(request.POST.get('cantidad', ''))
            precio_costo = int(request.POST.get('precio_costo', ''))
            precio_venta = int(request.POST.get('precio_venta', ''))
        except ValueError:
            mensaje_error = "La cantidad y los precios deben ser números enteros."
        else:
            if not nombre:
                mensaje_error = "El nombre del producto es obligatorio."
            elif cantidad < 0 or precio_costo < 0 or precio_venta < 0:
                mensaje_error = "La cantidad y los precios no pueden ser negativos."
            elif Producto.objects.filter(dueno=request.pyme, nombre__iexact=nombre).exists():
                mensaje_error = f"Ya tienes un producto llamado '{nombre}'."
            else:
                Producto.objects.create(
                    dueno=request.pyme,
                    nombre=nombre,
                    cantidad_actual=cantidad,
                    precio_costo=precio_costo,
                    precio_venta=precio_venta,
                )
                messages.success(request, f"Producto '{nombre}' creado.")
                return redirect('menu')

    return render(request, 'gestion/crear_producto.html', {
        'mensaje_error': mensaje_error,
        'datos': request.POST if request.method == 'POST' else {},
    })


@pyme_requerida
def editar_producto(request, producto_id):
    # Solo se pueden editar productos de la PYME con sesión iniciada.
    producto = get_object_or_404(Producto, id=producto_id, dueno=request.pyme)

    # Pantalla a la que se vuelve al terminar (solo se aceptan estas dos).
    volver = request.POST.get('volver') or request.GET.get('volver')
    if volver not in ('menu', 'stock'):
        volver = 'menu'

    mensaje_error = ""
    datos = {
        'nombre': producto.nombre,
        'agregar': 0,
        'precio_costo': producto.precio_costo,
        'precio_venta': producto.precio_venta,
    }

    if request.method == 'POST':
        datos = request.POST
        nombre = request.POST.get('nombre', '').strip()

        try:
            agregar = int(request.POST.get('agregar') or 0)
            precio_costo = int(request.POST.get('precio_costo', ''))
            precio_venta = int(request.POST.get('precio_venta', ''))
        except ValueError:
            mensaje_error = "Las unidades y los precios deben ser números enteros."
        else:
            if not nombre:
                mensaje_error = "El nombre del producto es obligatorio."
            elif agregar < 0 or precio_costo < 0 or precio_venta < 0:
                mensaje_error = "Las unidades y los precios no pueden ser negativos."
            elif (Producto.objects.filter(dueno=request.pyme, nombre__iexact=nombre)
                  .exclude(pk=producto.pk).exists()):
                mensaje_error = f"Ya tienes otro producto llamado '{nombre}'."
            else:
                # F() suma en la base de datos: no pisa ventas que ocurran al mismo tiempo.
                Producto.objects.filter(pk=producto.pk).update(
                    nombre=nombre,
                    cantidad_actual=F('cantidad_actual') + agregar,
                    precio_costo=precio_costo,
                    precio_venta=precio_venta,
                )
                texto = f"Producto '{nombre}' actualizado."
                if agregar:
                    texto += f" Se agregaron {agregar} unidades."
                messages.success(request, texto)
                return redirect(volver)

    return render(request, 'gestion/editar_producto.html', {
        'producto': producto,
        'datos': datos,
        'volver': volver,
        'mensaje_error': mensaje_error,
    })


@require_POST
@pyme_requerida
def eliminar_producto(request, producto_id):
    # Solo se pueden eliminar productos de la PYME con sesión iniciada.
    producto = get_object_or_404(Producto, id=producto_id, dueno=request.pyme)
    nombre = producto.nombre
    producto.delete()
    messages.success(request, f"Producto '{nombre}' eliminado.")

    destino = reverse('menu')
    q = request.POST.get('q', '').strip()
    if q:
        destino += '?' + urlencode({'q': q})
    return redirect(destino)


@pyme_requerida
def vista_stock(request):
    productos = Producto.objects.filter(dueno=request.pyme).order_by('nombre')
    return render(request, 'gestion/stock.html', {'resultados': productos, 'umbral': UMBRAL_STOCK_BAJO})


# ---------------------------------------------------------------- ventas

def _buscar_producto_para_venta(pyme, texto):
    """Devuelve (producto, error). Primero busca el nombre exacto; si no hay,
    acepta una coincidencia parcial solo cuando es única."""
    productos = Producto.objects.filter(dueno=pyme)

    exacto = productos.filter(nombre__iexact=texto).first()
    if exacto:
        return exacto, ""

    parciales = list(productos.filter(nombre__icontains=texto)[:2])
    if len(parciales) == 1:
        return parciales[0], ""
    if len(parciales) > 1:
        return None, f"Hay varios productos que coinciden con '{texto}'. Escribe el nombre completo."
    return None, f"No se encontró el producto '{texto}'."


def _fecha_de_venta(texto, hoy):
    """Devuelve (fecha_hora, error). Vacío o de hoy = ahora; otro día = ese día a la hora actual."""
    if not texto:
        return timezone.now(), ""
    dia = est.parsear_dia(texto)
    if dia is None:
        return None, "La fecha de la venta no es válida."
    if dia > hoy:
        return None, "La fecha de la venta no puede ser futura."
    if dia == hoy:
        return timezone.now(), ""
    ahora_local = timezone.localtime()
    return timezone.make_aware(datetime.combine(dia, ahora_local.time()), ahora_local.tzinfo), ""


@pyme_requerida
def vista_ventas(request):
    mensaje_error = ""
    hoy = timezone.localdate()

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'borrar':
            return redirect('ventas')

        if accion == 'confirmar':
            texto = request.POST.get('q', '').strip()

            try:
                cantidad = int(request.POST.get('cantidad', '0'))
            except ValueError:
                cantidad = 0

            fecha_venta, mensaje_error = _fecha_de_venta(request.POST.get('fecha', '').strip(), hoy)

            if mensaje_error:
                pass
            elif not texto:
                mensaje_error = "Debes ingresar el nombre de un producto."
            elif cantidad <= 0:
                mensaje_error = "La cantidad a vender debe ser mayor a 0."
            else:
                producto, mensaje_error = _buscar_producto_para_venta(request.pyme, texto)

                if producto:
                    with transaction.atomic():
                        # Se vuelve a leer con bloqueo para no vender stock que
                        # otra petición acaba de descontar.
                        producto = Producto.objects.select_for_update().get(pk=producto.pk)

                        if producto.cantidad_actual < cantidad:
                            mensaje_error = f"Stock insuficiente. Solo quedan {producto.cantidad_actual} unds."
                        else:
                            producto.cantidad_actual -= cantidad
                            producto.save(update_fields=['cantidad_actual'])
                            Venta.objects.create(
                                pyme=request.pyme,
                                producto=producto,
                                nombre_producto=producto.nombre,
                                cantidad=cantidad,
                                precio_unitario=producto.precio_venta,
                                ganancia=(producto.precio_venta - producto.precio_costo) * cantidad,
                                fecha=fecha_venta,
                            )

                    if not mensaje_error:
                        messages.success(request, "¡Venta registrada con éxito!")
                        return redirect('ventas')

    ventas = Venta.objects.filter(pyme=request.pyme)
    total = ventas.aggregate(total=Sum('ganancia'))['total'] or 0

    return render(request, 'gestion/ventas.html', {
        'ventas': [{
            'fecha': timezone.localtime(v.fecha).strftime('%d/%m/%Y %H:%M'),
            'nombre': v.nombre_producto,
            'cantidad': v.cantidad,
            'precio_txt': est.moneda(v.precio_unitario),
        } for v in ventas],
        'ganancias_texto': est.moneda(total),
        'mensaje_error': mensaje_error,
        'hoy_iso': hoy.isoformat(),
    })


# ---------------------------------------------------------------- perfil

def _extension_imagen(cabecera):
    """Reconoce el tipo real de la imagen por sus primeros bytes (no por el nombre)."""
    if cabecera.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if cabecera[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if cabecera[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if cabecera[:4] == b'RIFF' and cabecera[8:12] == b'WEBP':
        return '.webp'
    return None


@pyme_requerida
def perfil(request):
    pyme = request.pyme
    errores = {}
    datos = {'nombre_pyme': pyme.nombre_pyme, 'correo': pyme.correo}

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'datos':
            datos = request.POST
            nombre = request.POST.get('nombre_pyme', '').strip()
            correo = request.POST.get('correo', '').strip().lower()
            contrasena_actual = request.POST.get('contrasena_actual', '')
            cambia_correo = correo != pyme.correo.lower()

            try:
                validate_email(correo)
                correo_valido = True
            except ValidationError:
                correo_valido = False

            if not nombre:
                errores['datos'] = "El nombre de la PYME es obligatorio."
            elif len(nombre) > 100:
                errores['datos'] = "El nombre de la PYME no puede superar los 100 caracteres."
            elif not correo_valido:
                errores['datos'] = "Ingresa un correo válido."
            elif cambia_correo and not pyme.verificar_contrasena(contrasena_actual):
                errores['datos'] = "Para cambiar el correo debes ingresar tu contraseña actual."
            elif cambia_correo and PerfilPyme.objects.filter(correo__iexact=correo).exclude(pk=pyme.pk).exists():
                errores['datos'] = "Ya existe otra cuenta con ese correo."
            else:
                pyme.nombre_pyme = nombre
                pyme.correo = correo
                try:
                    pyme.save(update_fields=['nombre_pyme', 'correo'])
                except IntegrityError:
                    errores['datos'] = "Ya existe otra cuenta con ese correo."
                else:
                    request.session['nombre_pyme'] = nombre
                    messages.success(request, "Datos de la cuenta actualizados.")
                    return redirect('perfil')

        elif accion == 'foto':
            archivo = request.FILES.get('foto')
            if not archivo:
                errores['foto'] = "Elige una imagen para subir."
            elif archivo.size > MAX_FOTO_BYTES:
                errores['foto'] = "La imagen no puede pesar más de 2 MB."
            else:
                extension = _extension_imagen(archivo.read(16))
                archivo.seek(0)
                if not extension:
                    errores['foto'] = "El archivo debe ser una imagen JPG, PNG, GIF o WEBP."
                else:
                    if pyme.foto:
                        pyme.foto.delete(save=False)
                    pyme.foto.save(f"{uuid.uuid4().hex}{extension}", archivo, save=True)
                    messages.success(request, "Foto de perfil actualizada.")
                    return redirect('perfil')

        elif accion == 'quitar_foto':
            if pyme.foto:
                pyme.foto.delete(save=True)
            messages.success(request, "Foto de perfil eliminada.")
            return redirect('perfil')

        elif accion == 'contrasena':
            actual = request.POST.get('contrasena_actual', '')
            nueva = request.POST.get('contrasena_nueva', '')
            repetida = request.POST.get('contrasena_repetida', '')

            if not pyme.verificar_contrasena(actual):
                errores['contrasena'] = "La contraseña actual no es correcta."
            elif nueva != repetida:
                errores['contrasena'] = "La nueva contraseña y su repetición no coinciden."
            elif nueva == actual:
                errores['contrasena'] = "La nueva contraseña debe ser distinta de la actual."
            else:
                try:
                    validate_password(nueva)
                except ValidationError as error:
                    errores['contrasena'] = " ".join(error.messages)
                else:
                    pyme.set_password(nueva)
                    pyme.save(update_fields=['contrasena'])
                    # La sesión actual sigue activa; cualquier otra sesión abierta queda cerrada.
                    request.session.cycle_key()
                    request.session['sello'] = _sello(pyme)
                    messages.success(request, "Contraseña actualizada. Las demás sesiones abiertas se cerraron.")
                    return redirect('perfil')

    return render(request, 'gestion/perfil.html', {
        'pyme': pyme,
        'datos': datos,
        'errores': errores,
    })
