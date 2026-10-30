from django.shortcuts import render

INVENTARIO_PRUEBA = [
    {'id': 1, 'nombre': 'Manzanas', 'stock': 50, 'precio': 1000},
    {'id': 2, 'nombre': 'Naranjas', 'stock': 15, 'precio': 1200},
    {'id': 3, 'nombre': 'Plátanos', 'stock': 0, 'precio': 800},
]

def pantalla_inicio(request):
    return render(request, 'gestion/login.html')

def registro(request):
    return render(request, 'gestion/registro.html')

def dashboard(request):
    return render(request, 'gestion/dashboard.html')

def menu_principal(request):
    query = request.GET.get('q', '')
    resultados = []
    mensaje_error = ""

    if query:
        for producto in INVENTARIO_PRUEBA:
            if query.lower() in producto['nombre'].lower():
                resultados.append(producto)
        if not resultados:
            mensaje_error = f"No se encontró el producto '{query}' en el inventario."

    context = {'query': query, 'resultados': resultados, 'mensaje_error': mensaje_error}
    return render(request, 'gestion/menu_principal.html', context)

def vista_stock(request):
    resultados = []
    inventario_procesado = []

    for prod in INVENTARIO_PRUEBA:
        precio_con_iva = prod['precio'] * 1.19
        precio_salida = precio_con_iva * 1.40

        prod_temp = prod.copy()
        prod_temp['precio_salida'] = int(precio_salida)
        inventario_procesado.append(prod_temp)

    resultados = inventario_procesado
    context = {'resultados': resultados}
    return render(request, 'gestion/stock.html', context)

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

            if not query:
                mensaje_error = "Debes ingresar el nombre de un producto."
            elif cantidad_a_vender <= 0:
                mensaje_error = "La cantidad a vender debe ser mayor a 0."
            else:
                
                producto_encontrado = None
                for prod in INVENTARIO_PRUEBA:
                    if query.lower() in prod['nombre'].lower():
                        producto_encontrado = prod
                        break
                
                if not producto_encontrado:
                    mensaje_error = f"No se encontró el producto '{query}'."
                elif producto_encontrado['stock'] < cantidad_a_vender:
                    mensaje_error = f"Stock insuficiente. Solo quedan {producto_encontrado['stock']} unds."
                else:
                    
                    producto_encontrado['stock'] -= cantidad_a_vender
                    
                    precio_con_iva = producto_encontrado['precio'] * 1.19
                    precio_salida = precio_con_iva * 1.40
                    ganancia_venta = int(precio_salida * cantidad_a_vender)
                    
                    GANANCIAS_TOTALES += ganancia_venta

                    
                    HISTORIAL_VENTAS.append({
                        'nombre': producto_encontrado['nombre'],
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