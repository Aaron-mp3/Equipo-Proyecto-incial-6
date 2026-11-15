from django.shortcuts import render, redirect
from .models import PerfilPyme, PerfilDueno, Producto

def pantalla_inicio(request):
    mensaje_error = ""
    
    if request.method == 'POST':
        correo_ingresado = request.POST.get('correo')
        contrasena_ingresada = request.POST.get('contrasena')

        pyme = PerfilPyme.objects.filter(correo=correo_ingresado, contrasena=contrasena_ingresada).first()

        if pyme:
            request.session['pyme_id'] = pyme.id
            request.session['nombre_pyme'] = pyme.nombre_pyme 
            return redirect('menu_principal')
        else:
            mensaje_error = "Correo o contraseña incorrectos."

    context = {'mensaje_error': mensaje_error}
    return render(request, 'gestion/login.html', context)

def registro(request):
    if request.method == 'POST':
        n_pyme = request.POST.get('nombre_pyme')
        corr = request.POST.get('correo')
        passw = request.POST.get('contrasena')

        PerfilPyme.objects.create(
            nombre_pyme=n_pyme,
            correo=corr,
            contrasena=passw
        )
        return redirect('inicio')

    return render(request, 'gestion/registro.html')

def dashboard(request):
    return render(request, 'gestion/dashboard.html')

def menu_principal(request):
    query = request.GET.get('q', '') # Mantenemos 'q' para que coincida con tu input de búsqueda HTML
    resultados = []
    mensaje_error = ""

    # Obtenemos el ID de la pyme/dueño actual desde la sesión
    pyme_id = request.session.get('pyme_id')

    if query and pyme_id:
        perfil_dueno = PerfilDueno.objects.filter(id=pyme_id).first()
        if perfil_dueno:
            # Buscamos en la base de datos filtrando por el dueño y el nombre del producto
            resultados = Producto.objects.filter(dueno=perfil_dueno, nombre__icontains=query)
    
    if query and not resultados:
        mensaje_error = f"No se encontró el producto '{query}' en el inventario."

    context = {
        'query': query,
        'resultados': resultados,
        'mensaje_error': mensaje_error
    }
    return render(request, 'gestion/menu_principal.html', context)

def vista_stock(request):
    resultados = []
    inventario_procesado = []

    pyme_id = request.session.get('pyme_id')
    if pyme_id:
        perfil_dueno = PerfilDueno.objects.filter(id=pyme_id).first()
        if perfil_dueno:
            # Obtenemos los productos reales de la base de datos de este usuario
            productos_bd = Producto.objects.filter(dueno=perfil_dueno)
            
            for prod in productos_bd:
                # Calculamos precios con IVA y salida dinámicamente
                precio_con_iva = prod.precio_costo * 1.19 if hasattr(prod, 'precio_costo') else 1000 * 1.19
                precio_salida = precio_con_iva * 1.40

                # Convertimos el objeto de base de datos a diccionario para compatibilidad con tu HTML
                prod_temp = {
                    'nombre': prod.nombre,
                    'stock': prod.cantidad_actual,
                    'precio': prod.precio_costo if hasattr(prod, 'precio_costo') else 1000,
                    'precio_salida': int(precio_salida)
                }
                inventario_procesado.append(prod_temp)
                
    resultados = inventario_procesado
    context = {'resultados': resultados}
    return render(request, 'gestion/stock.html', context)

# Historial y ganancias globales (puedes adaptarlas a modelos más adelante si lo deseas)
HISTORIAL_VENTAS = []
GANANCIAS_TOTALES = 0

def vista_ventas(request):
    global GANANCIAS_TOTALES
    mensaje_error = ""
    mensaje_exito = ""

    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'borrar':
            pass
        elif accion == 'confirmar':
            query = request.POST.get('q', '').strip()
            cantidad_str = request.POST.get('cantidad', '0')

            try:
                cantidad_a_vender = int(cantidad_str)
            except ValueError:
                cantidad_a_vender = 0

            pyme_id = request.session.get('pyme_id')
            perfil_dueno = PerfilDueno.objects.filter(id=pyme_id).first() if pyme_id else None

            if not query:
                mensaje_error = "Debes ingresar el nombre de un producto."
            elif cantidad_a_vender <= 0:
                mensaje_error = "La cantidad a vender debe ser mayor a 0."
            elif not perfil_dueno:
                mensaje_error = "No hay una sesión de PYME activa."
            else:
                # Buscamos el producto en la base de datos del usuario
                producto_encontrado = Producto.objects.filter(dueno=perfil_dueno, nombre__icontains=query).first()
                
                if not producto_encontrado:
                    mensaje_error = f"No se encontró el producto '{query}'."
                elif producto_encontrado.cantidad_actual < cantidad_a_vender:
                    mensaje_error = f"Stock insuficiente. Solo quedan {producto_encontrado.cantidad_actual} unds."
                else:
                    # Descontamos stock en la base de datos
                    producto_encontrado.cantidad_actual -= cantidad_a_vender
                    producto_encontrado.save()
                    
                    precio_base = producto_encontrado.precio_costo if hasattr(producto_encontrado, 'precio_costo') else 1000
                    precio_con_iva = precio_base * 1.19
                    precio_salida = precio_con_iva * 1.40
                    ganancia_venta = int(precio_salida * cantidad_a_vender)
                    
                    GANANCIAS_TOTALES += ganancia_venta

                    HISTORIAL_VENTAS.append({
                        'nombre': producto_encontrado.nombre,
                        'cantidad': cantidad_a_vender,
                        'precio_venta': int(precio_salida)
                    })
                    mensaje_exito = "¡Venta registrada con éxito!"

    context = {
        'ventas': HISTORIAL_VENTAS,
        'ganancias_totales': GANANCIAS_TOTALES,
        'mensaje_error': mensaje_error,
        'mensaje_exito': mensaje_exito
    }
    return render(request, 'gestion/ventas.html', context)

def crear_producto(request):
    mensaje_error = ""
    
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        cantidad = request.POST.get('cantidad')
        precio_venta_str = request.POST.get('precio') # Capturamos el precio ingresado

        pyme_id = request.session.get('pyme_id')
        if not pyme_id:
            primera_pyme = PerfilPyme.objects.first()
            if primera_pyme:
                pyme_id = primera_pyme.id
                request.session['pyme_id'] = pyme_id
            else:
                mensaje_error = "No hay ninguna PYME registrada."

        if not mensaje_error and (not nombre or not cantidad or not precio_venta_str):
            mensaje_error = "Por favor completa todos los campos (el precio es obligatorio)."
        elif not mensaje_error:
            perfil_dueno, creado = PerfilDueno.objects.get_or_create(id=pyme_id)

            try:
                precio_venta = float(precio_venta_str)

                # Creamos el producto guardando directamente el precio ingresado como precio_venta
                Producto.objects.create(
                    nombre=nombre,
                    cantidad_actual=int(cantidad),
                    precio_costo=precio_venta, # Opcional: si tu modelo exige precio_costo, le asignamos el mismo valor
                    precio_venta=precio_venta, # ¡Aquí va el precio directo del usuario!
                    dueno=perfil_dueno
                )
                
                # Te redirige de vuelta al menú principal con el producto creado
                return redirect('menu') 
                
            except ValueError:
                mensaje_error = "La cantidad y el precio deben ser valores numéricos válidos."

    context = {'mensaje_error': mensaje_error}
    return render(request, 'gestion/crear_producto.html', context)