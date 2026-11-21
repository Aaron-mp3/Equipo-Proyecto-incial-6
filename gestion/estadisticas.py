"""Cálculos de ganancias por día, calendario y tendencias.

No depende de Django: recibe datos simples (fechas y números) para poder
probarse por separado y mantener las vistas cortas.
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta

NOMBRES_MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
NOMBRES_DIAS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')

VACIO = {'ventas': 0, 'unidades': 0, 'ingresos': 0, 'ganancia': 0}

# metrica -> (texto en plural para frases, etiqueta corta)
METRICAS = {
    'ganancia': ('las ganancias', 'Ganancias'),
    'ingresos': ('las ventas', 'Ventas ($)'),
}


def moneda(valor):
    return f"-${abs(valor)}" if valor < 0 else f"${valor}"


def fecha_larga(d):
    return f"{NOMBRES_DIAS[d.weekday()]} {d.day} de {NOMBRES_MESES[d.month - 1]} de {d.year}"


# ------------------------------------------------------------- agrupación

def agrupar_por_dia(ventas):
    """ventas: iterable de (dia, cantidad, precio_unitario, ganancia).

    Devuelve {dia: {'ventas', 'unidades', 'ingresos', 'ganancia'}}.
    """
    por_dia = defaultdict(lambda: dict(VACIO))
    for dia, cantidad, precio_unitario, ganancia in ventas:
        datos = por_dia[dia]
        datos['ventas'] += 1
        datos['unidades'] += cantidad
        datos['ingresos'] += cantidad * precio_unitario
        datos['ganancia'] += ganancia
    return dict(por_dia)


def sumar_periodo(por_dia, desde, hasta):
    """Suma los días desde..hasta (ambos incluidos)."""
    total = dict(VACIO)
    dia = desde
    while dia <= hasta:
        datos = por_dia.get(dia)
        if datos:
            for clave in total:
                total[clave] += datos[clave]
        dia += timedelta(days=1)
    return total


# ------------------------------------------------------------- tendencias

def variacion(actual, anterior):
    """Devuelve (tendencia, porcentaje) con tendencia 'sube', 'baja' o 'igual'.

    El porcentaje es None cuando antes no había nada con qué comparar.
    """
    if actual == anterior:
        return 'igual', 0
    if anterior == 0:
        return ('sube' if actual > 0 else 'baja'), None
    porcentaje = round(abs(actual - anterior) / abs(anterior) * 100, 1)
    if porcentaje == int(porcentaje):
        porcentaje = int(porcentaje)
    return ('sube' if actual > anterior else 'baja'), porcentaje


def comparar_periodos(por_dia, hoy, dias, metrica, nombre_anterior):
    """Compara los últimos `dias` días (hasta hoy) con los `dias` anteriores."""
    actual = sumar_periodo(por_dia, hoy - timedelta(days=dias - 1), hoy)[metrica]
    anterior = sumar_periodo(por_dia, hoy - timedelta(days=2 * dias - 1), hoy - timedelta(days=dias))[metrica]
    tendencia, porcentaje = variacion(actual, anterior)

    porcentaje_txt = '' if porcentaje is None else str(porcentaje).replace('.', ',')
    sujeto = METRICAS[metrica][0]
    if tendencia == 'igual':
        resumen = f"Sin cambios en {sujeto} respecto a {nombre_anterior}."
    else:
        verbo = 'subieron' if tendencia == 'sube' else 'bajaron'
        if porcentaje is None:
            resumen = f"{sujeto.capitalize()} {verbo}: no había ventas {nombre_anterior}."
        else:
            resumen = f"{sujeto.capitalize()} {verbo} {porcentaje_txt}% respecto a {nombre_anterior}."

    maximo = max(abs(actual), abs(anterior), 1)
    return {
        'tendencia': tendencia,
        'porcentaje': porcentaje,
        'porcentaje_txt': porcentaje_txt,
        'resumen': resumen,
        'actual': actual,
        'anterior': anterior,
        'actual_txt': moneda(actual),
        'anterior_txt': moneda(anterior),
        'alto_actual': round(abs(actual) / maximo * 100),
        'alto_anterior': round(abs(anterior) / maximo * 100),
    }


def serie_diaria(por_dia, hoy, dias, metrica):
    """Barras de los últimos `dias` días, con su posición en % para dibujarlas.

    Admite valores negativos: la línea base sube lo necesario.
    """
    fechas = [hoy - timedelta(days=i) for i in range(dias - 1, -1, -1)]
    valores = [por_dia.get(f, VACIO)[metrica] for f in fechas]
    max_pos = max([v for v in valores if v > 0], default=0)
    max_neg = max([-v for v in valores if v < 0], default=0)
    espacio = (max_pos + max_neg) or 1
    base = max_neg / espacio * 100

    barras = []
    for f, v in zip(fechas, valores):
        alto = abs(v) / espacio * 100
        if v != 0:
            alto = max(alto, 1.5)  # que una venta pequeña igual se vea
        inicio = base if v >= 0 else base - alto
        barras.append({
            'fecha': f,
            'dia': f.day,
            'etiqueta': f"{f.day:02d}/{f.month:02d}",
            'valor': v,
            'texto': moneda(v),
            'inicio': round(inicio, 2),
            'alto': round(alto, 2),
            'inicio_css': f"{inicio:.2f}",
            'alto_css': f"{alto:.2f}",
            'negativo': v < 0,
            'es_hoy': f == hoy,
            'mostrar_etiqueta': (hoy - f).days % 5 == 0,
        })
    return {'barras': barras, 'base': round(base, 2), 'base_css': f"{base:.2f}", 'maximo_txt': moneda(max_pos)}


# --------------------------------------------------------------- calendario

def parsear_mes(texto, hoy):
    """'2026-11' -> (2026, 11). Si no es válido o es futuro, devuelve el mes de hoy."""
    try:
        anio, mes = (int(x) for x in texto.split('-'))
        if 2000 <= anio <= 2100 and 1 <= mes <= 12 and (anio, mes) <= (hoy.year, hoy.month):
            return anio, mes
    except (AttributeError, ValueError):
        pass
    return hoy.year, hoy.month


def parsear_dia(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def mes_vecino(anio, mes, delta):
    indice = anio * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def texto_mes(anio, mes):
    return f"{anio}-{mes:02d}"


def construir_calendario(por_dia, anio, mes, hoy, seleccionado=None):
    """Semanas (lunes a domingo) con los datos de cada día del mes."""
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        fila = []
        for d in semana:
            datos = por_dia.get(d)
            ganancia = datos['ganancia'] if datos else None
            fila.append({
                'fecha': d,
                'iso': d.isoformat(),
                'dia': d.day,
                'del_mes': d.month == mes,
                'futuro': d > hoy,
                'es_hoy': d == hoy,
                'seleccionado': d == seleccionado,
                'ventas': datos['ventas'] if datos else 0,
                'ganancia': ganancia,
                'ganancia_txt': moneda(ganancia) if ganancia is not None else '',
                'clase': ('positivo' if ganancia > 0 else 'negativo' if ganancia < 0 else 'neutro')
                         if ganancia is not None else 'vacio',
            })
        semanas.append(fila)
    return semanas


def resumen_mes(por_dia, anio, mes):
    """Totales del mes y su mejor día."""
    dias = {d: v for d, v in por_dia.items() if d.year == anio and d.month == mes}
    total = dict(VACIO)
    for datos in dias.values():
        for clave in total:
            total[clave] += datos[clave]
    mejor = max(dias.items(), key=lambda par: par[1]['ganancia'], default=None)
    return {
        'ganancia_txt': moneda(total['ganancia']),
        'ventas': total['ventas'],
        'unidades': total['unidades'],
        'mejor_dia': (f"{mejor[0].day} de {NOMBRES_MESES[mes - 1]} ({moneda(mejor[1]['ganancia'])})"
                      if mejor and mejor[1]['ganancia'] > 0 else '—'),
    }
