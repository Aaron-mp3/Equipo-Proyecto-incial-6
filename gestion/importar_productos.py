"""Convierte una hoja leída de un Excel en productos listos para cargar.

Módulo sin dependencias de Django (se puede probar solo). Trabaja con el
resultado de `lector_excel.leer_xlsx`: cada celda es (texto, es_numero).

La primera fila con datos debe ser el encabezado y traer estas columnas
(en cualquier orden; las tildes y mayúsculas no importan):
    Producto | Cantidad | Precio compra | Precio venta
También se reconocen sinónimos: Nombre, Stock, Unidades, Costo, Precio, etc.
"""
import re
import unicodedata

MAX_NOMBRE = 150          # largo del campo nombre en el modelo
MAX_ENTERO = 2_000_000_000
MAX_INT_BD = 2_147_483_647

COLUMNAS = {
    'nombre': {'producto', 'nombre', 'nombre producto', 'nombre del producto', 'articulo', 'item', 'descripcion'},
    'cantidad': {'cantidad', 'stock', 'unidades', 'existencias', 'cant', 'cantidad actual', 'stock actual'},
    'costo': {'precio compra', 'precio de compra', 'costo', 'precio costo', 'precio de costo', 'compra', 'costo unitario'},
    'venta': {'precio venta', 'precio de venta', 'venta', 'precio', 'pvp', 'precio publico', 'precio al publico'},
}
ETIQUETAS = {'nombre': 'Producto', 'cantidad': 'Cantidad', 'costo': 'Precio compra', 'venta': 'Precio venta'}


def _normalizar(texto):
    sin_tildes = ''.join(c for c in unicodedata.normalize('NFD', texto or '') if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', sin_tildes.lower()).strip()


def clave_nombre(nombre):
    """Clave para comparar nombres de producto sin distinguir mayúsculas ni espacios sobrantes."""
    return ' '.join((nombre or '').split()).casefold()


def _numero(texto):
    t = (texto or '').strip().replace('$', '').replace(' ', '').replace(' ', '')
    if not t:
        raise ValueError('vacío')
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.')
    elif ',' in t:
        t = t.replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')
    valor = float(t)                      # ValueError si no es número
    if valor != valor or abs(valor) > 1e15:
        raise ValueError('fuera de rango')
    return valor


def _entero(texto, campo):
    try:
        valor = _numero(texto)
    except ValueError:
        raise ValueError(f"{campo} no es un número válido")
    if valor != int(valor):
        raise ValueError(f"{campo} debe ser un número entero")
    if valor < 0:
        raise ValueError(f"{campo} no puede ser menor que 0")
    if valor > MAX_ENTERO:
        raise ValueError(f"{campo} es demasiado grande")
    return int(valor)


def _texto(celda):
    return celda[0] if celda else ''


def analizar_hoja(hoja):
    """Devuelve {'ok', 'motivo', 'filas', 'errores'}.

    filas   -> [{'fila': n_excel, 'nombre', 'cantidad', 'costo', 'venta'}, ...] (ya validadas)
    errores -> [(n_excel, 'motivo'), ...] filas que no se pueden cargar
    """
    if hoja.get('truncada'):
        return {'ok': False, 'filas': [], 'errores': [],
                'motivo': "La hoja tiene demasiadas filas o columnas para cargarla de una vez. Divide el archivo en partes más pequeñas."}

    filas = hoja.get('filas', [])
    # La primera fila con algún dato (dentro de las primeras 10) es el encabezado.
    encabezado_idx = next((i for i, f in enumerate(filas[:10]) if any(_texto(c).strip() for c in f)), None)
    if encabezado_idx is None:
        return {'ok': False, 'filas': [], 'errores': [], 'motivo': "La hoja está vacía."}

    posiciones = {}
    for col, celda in enumerate(filas[encabezado_idx]):
        nombre_col = _normalizar(_texto(celda))
        for clave, sinonimos in COLUMNAS.items():
            if clave not in posiciones and nombre_col in sinonimos:
                posiciones[clave] = col
    faltan = [ETIQUETAS[k] for k in ('nombre', 'cantidad', 'costo', 'venta') if k not in posiciones]
    if faltan:
        return {'ok': False, 'filas': [], 'errores': [],
                'motivo': "Faltan estas columnas en la primera fila: " + ", ".join(faltan) + "."}

    validas, errores = [], []
    for i in range(encabezado_idx + 1, len(filas)):
        fila = filas[i]
        n_excel = i + 1
        if not any(_texto(c).strip() for c in fila):
            continue                              # fila vacía: se ignora
        def celda(clave):
            col = posiciones[clave]
            return _texto(fila[col]) if col < len(fila) else ''
        nombre = ' '.join(celda('nombre').split())
        try:
            if not nombre:
                raise ValueError("falta el nombre del producto")
            if len(nombre) > MAX_NOMBRE:
                raise ValueError(f"el nombre supera los {MAX_NOMBRE} caracteres")
            cantidad = _entero(celda('cantidad'), 'La cantidad')
            costo = _entero(celda('costo'), 'El precio de compra')
            venta = _entero(celda('venta'), 'El precio de venta')
        except ValueError as e:
            texto = str(e)
            errores.append((n_excel, texto[0].upper() + texto[1:]))
            continue
        validas.append({'fila': n_excel, 'nombre': nombre, 'cantidad': cantidad, 'costo': costo, 'venta': venta})

    if not validas:
        motivo = "No hay filas válidas para cargar." if errores else "La hoja no tiene productos debajo del encabezado."
        return {'ok': False, 'filas': [], 'errores': errores, 'motivo': motivo}
    return {'ok': True, 'motivo': '', 'filas': validas, 'errores': errores}


def consolidar(filas):
    """Une las filas con el mismo nombre: suma las cantidades y deja los últimos precios."""
    por_clave = {}
    orden = []
    for f in filas:
        k = clave_nombre(f['nombre'])
        if k not in por_clave:
            por_clave[k] = {'nombre': f['nombre'], 'cantidad': 0, 'costo': f['costo'], 'venta': f['venta'], 'repeticiones': 0}
            orden.append(k)
        item = por_clave[k]
        item['cantidad'] += f['cantidad']
        item['costo'], item['venta'] = f['costo'], f['venta']
        item['repeticiones'] += 1
    return [por_clave[k] for k in orden]


def previsualizar(filas, existentes):
    """Marca qué pasará con cada producto.

    existentes -> {clave_nombre: cantidad_actual} de los productos que ya tiene la PYME.
    """
    resultado = []
    for item in consolidar(filas):
        actual = existentes.get(clave_nombre(item['nombre']))
        fila = dict(item)
        if actual is None:
            fila.update(accion='nuevo', stock_final=item['cantidad'])
        else:
            fila.update(accion='suma', stock_final=actual + item['cantidad'])
        resultado.append(fila)
    return resultado
