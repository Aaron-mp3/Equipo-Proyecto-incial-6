from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import PerfilPyme, Producto, Venta


def pyme_requerida(vista):
    """Solo deja pasar si hay una PYME con sesión iniciada.

    Deja la PYME disponible como request.pyme.
    """
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        pyme = PerfilPyme.objects.filter(id=request.session.get('pyme_id')).first()
        if pyme is None:
            request.session.flush()
            return redirect('inicio')
        request.pyme = pyme
        return vista(request, *args, **kwargs)
    return envoltura


# ---------------------------------------------------------------- cuenta

def pantalla_inicio(request):
    mensaje_error = ""

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip()
        contrasena = request.POST.get('contrasena', '')

        pyme = PerfilPyme.objects.filter(correo__iexact=correo).first()

        if pyme and pyme.verificar_contrasena(contrasena):
            request.session.cycle_key()
            request.session['pyme_id'] = pyme.id
            request.session['nombre_pyme'] = pyme.nombre_pyme
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
    return redirect('inicio')


UMBRAL_STOCK_BAJO = 5  # productos con esta cantidad o menos se marcan como "stock bajo"


@pyme_requerida
def dashboard(request):
    productos = Producto.objects.filter(dueno=request.pyme)
    resumen = productos.aggregate(total=Count('id'), unidades=Sum('cantidad_actual'))
    ganancias = Venta.objects.filter(pyme=request.pyme).aggregate(total=Sum('ganancia'))['total'] or 0

    return render(request, 'gestion/dashboard.html', {
        'pyme': request.pyme,
        'total_productos': resumen['total'],
        'total_unidades': resumen['unidades'] or 0,
        'stock_bajo': productos.filter(cantidad_actual__lte=UMBRAL_STOCK_BAJO).count(),
        'ganancias': ganancias,
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
    return render(request, 'gestion/stock.html', {'resultados': productos})


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


@pyme_requerida
def vista_ventas(request):
    mensaje_error = ""

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

            if not texto:
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
                            )

                    if not mensaje_error:
                        messages.success(request, "¡Venta registrada con éxito!")
                        return redirect('ventas')

    ventas = Venta.objects.filter(pyme=request.pyme)
    ganancias = ventas.aggregate(total=Sum('ganancia'))['total'] or 0

    return render(request, 'gestion/ventas.html', {
        'ventas': ventas,
        'ganancias_totales': ganancias,
        'mensaje_error': mensaje_error,
    })
