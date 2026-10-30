from django.shortcuts import render

# 1. Datos precargados
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

# 2. VISTA DE PRODUCTOS (Restaurada: buscador simple sin cálculos)
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

# 3. NUEVA VISTA DE STOCK (Muestra todos, tiene botones +/- y precios calculados)
def vista_stock(request):
    query = request.GET.get('q', '')
    accion = request.GET.get('accion', '')
    producto_id = request.GET.get('id', '')

    if accion and producto_id:
        for prod in INVENTARIO_PRUEBA:
            if str(prod['id']) == str(producto_id):
                if accion == 'sumar':
                    prod['stock'] += 1
                elif accion == 'restar' and prod['stock'] > 0:
                    prod['stock'] -= 1
                break

    resultados = []
    mensaje_error = ""
    inventario_procesado = []

    for prod in INVENTARIO_PRUEBA:
        precio_con_iva = prod['precio'] * 1.19
        precio_salida = precio_con_iva * 1.40
        prod_temp = prod.copy()
        prod_temp['precio_salida'] = int(precio_salida)
        inventario_procesado.append(prod_temp)

    if query:
        for producto in inventario_procesado:
            if query.lower() in producto['nombre'].lower():
                resultados.append(producto)
        if not resultados:
            mensaje_error = f"No se encontró el producto '{query}' en el inventario."
    else:
        resultados = inventario_procesado

    context = {'query': query, 'resultados': resultados, 'mensaje_error': mensaje_error}
    return render(request, 'gestion/stock.html', context)