"""Lector de archivos Excel (.xlsx) sin dependencias externas.

Un .xlsx es un ZIP con archivos XML. Este módulo lo abre solo con la
biblioteca estándar de Python (zipfile + xml), así que no hace falta instalar
nada. Solo LEE: no guarda ni modifica el archivo.

Resultado de `leer_xlsx`: una lista de hojas, cada una un diccionario con
    nombre   -> nombre de la hoja
    filas    -> lista de filas; cada fila es una lista de (texto, es_numero)
    columnas -> cantidad de columnas mostradas
    total_filas / total_columnas -> tamaño real de la hoja
    truncada -> True si se cortó por los límites de seguridad
"""
import re
import zipfile
import datetime
import xml.etree.ElementTree as ET

MAX_FILAS = 500
MAX_COLUMNAS = 30
MAX_HOJAS = 10
MAX_BYTES_XML = 40 * 1024 * 1024        # tamaño máximo de cada parte XML ya descomprimida
MAX_BYTES_TOTAL = 120 * 1024 * 1024     # tamaño total descomprimido (protege de "zip bombs")

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
NS_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
NS_PKG_REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'

# Formatos de fecha/hora incorporados en Excel
_FORMATOS_FECHA = set(range(14, 23)) | {27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58}


class ErrorExcel(Exception):
    """El archivo no se pudo leer; el mensaje se puede mostrar al usuario."""


def _leer_parte(zf, nombre, obligatoria=False):
    try:
        info = zf.getinfo(nombre)
    except KeyError:
        if obligatoria:
            raise ErrorExcel("El archivo no parece un libro de Excel (.xlsx) válido.")
        return None
    if info.file_size > MAX_BYTES_XML:
        raise ErrorExcel("El archivo es demasiado grande para leerlo aquí.")
    return zf.read(nombre)


def _parsear(datos):
    # Rechaza XML con definiciones de entidades (ataques "billion laughs" y similares).
    if b'<!DOCTYPE' in datos[:2048].upper() or b'<!ENTITY' in datos.upper():
        raise ErrorExcel("El archivo contiene datos no permitidos.")
    try:
        return ET.fromstring(datos)
    except ET.ParseError:
        raise ErrorExcel("El archivo está dañado o no es un .xlsx válido.")


def _texto_si(si):
    """Texto de un <si> de sharedStrings (ignora la fonética <rPh>)."""
    partes = []
    for hijo in si:
        if hijo.tag == NS + 't':
            partes.append(hijo.text or '')
        elif hijo.tag == NS + 'r':
            for t in hijo.findall(NS + 't'):
                partes.append(t.text or '')
    return ''.join(partes)


def _cadenas_compartidas(zf):
    datos = _leer_parte(zf, 'xl/sharedStrings.xml')
    if datos is None:
        return []
    raiz = _parsear(datos)
    return [_texto_si(si) for si in raiz.findall(NS + 'si')]


def _formato_es_fecha(codigo):
    # Quita textos entre comillas y secciones [..] y busca letras de fecha/hora.
    limpio = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', codigo or '').lower()
    return bool(re.search(r'[dmyhs]', limpio)) and not re.search(r'^(general|0|#)', limpio)


def _estilos_fecha(zf):
    """Conjunto de índices de estilo (cellXfs) cuyo formato es fecha u hora."""
    datos = _leer_parte(zf, 'xl/styles.xml')
    if datos is None:
        return set()
    raiz = _parsear(datos)
    personalizados = {}
    formatos = raiz.find(NS + 'numFmts')
    if formatos is not None:
        for f in formatos.findall(NS + 'numFmt'):
            try:
                personalizados[int(f.get('numFmtId'))] = f.get('formatCode', '')
            except (TypeError, ValueError):
                continue
    resultado = set()
    xfs = raiz.find(NS + 'cellXfs')
    if xfs is not None:
        for i, xf in enumerate(xfs.findall(NS + 'xf')):
            try:
                id_formato = int(xf.get('numFmtId', 0))
            except ValueError:
                continue
            if id_formato in personalizados:
                if _formato_es_fecha(personalizados[id_formato]):
                    resultado.add(i)
            elif id_formato in _FORMATOS_FECHA:
                resultado.add(i)
    return resultado


def _numero_a_texto(valor):
    """Número de Excel -> texto con coma decimal (ej. 1234.5 -> '1234,5')."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return valor
    if numero != numero or numero in (float('inf'), float('-inf')):
        return valor
    if numero == int(numero) and abs(numero) < 1e15:
        return str(int(numero))
    return ('%.10g' % numero).replace('.', ',')


def _fecha_a_texto(valor):
    try:
        serie = float(valor)
        base = datetime.datetime(1899, 12, 30)
        momento = base + datetime.timedelta(days=serie)
    except (TypeError, ValueError, OverflowError):
        return _numero_a_texto(valor)
    if serie == int(serie):
        return momento.strftime('%d/%m/%Y')
    if serie < 1:
        return momento.strftime('%H:%M')
    return momento.strftime('%d/%m/%Y %H:%M')


def _indice_columna(referencia):
    """'B3' -> 1 (columna B, base 0)."""
    letras = re.match(r'[A-Za-z]+', referencia or '')
    if not letras:
        return None
    n = 0
    for ch in letras.group(0).upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _valor_celda(c, compartidas, estilos_fecha):
    """Devuelve (texto, es_numero) o None si la celda está vacía."""
    tipo = c.get('t')
    if tipo == 'inlineStr':
        is_ = c.find(NS + 'is')
        texto = _texto_si(is_) if is_ is not None else ''
        return (texto, False) if texto != '' else None
    v = c.find(NS + 'v')
    if v is None or v.text is None or v.text == '':
        return None
    crudo = v.text
    if tipo == 's':
        try:
            return (compartidas[int(crudo)], False)
        except (ValueError, IndexError):
            return None
    if tipo == 'b':
        return ('VERDADERO' if crudo.strip() == '1' else 'FALSO', False)
    if tipo == 'e':
        return (crudo, False)
    if tipo in ('str', 'd'):
        return (crudo, False)
    # número (tipo 'n' o sin tipo)
    try:
        estilo = int(c.get('s', 0))
    except ValueError:
        estilo = 0
    if estilo in estilos_fecha:
        return (_fecha_a_texto(crudo), False)
    return (_numero_a_texto(crudo), True)


def _leer_hoja(datos, compartidas, estilos_fecha, nombre):
    raiz = _parsear(datos)
    datos_hoja = raiz.find(NS + 'sheetData')
    celdas = {}              # {fila: {columna: (texto, es_numero)}}
    max_fila = 0
    max_col = -1
    truncada = False
    if datos_hoja is not None:
        siguiente_fila = 0
        for fila in datos_hoja.findall(NS + 'row'):
            try:
                numero = int(fila.get('r')) if fila.get('r') else siguiente_fila + 1
            except ValueError:
                numero = siguiente_fila + 1
            siguiente_fila = numero
            siguiente_col = 0
            fila_celdas = {}
            for c in fila.findall(NS + 'c'):
                col = _indice_columna(c.get('r'))
                if col is None:
                    col = siguiente_col
                siguiente_col = col + 1
                valor = _valor_celda(c, compartidas, estilos_fecha)
                if valor is None:
                    continue
                fila_celdas[col] = valor
                if col > max_col:
                    max_col = col
            if fila_celdas:
                celdas[numero] = fila_celdas
                if numero > max_fila:
                    max_fila = numero

    total_filas = max_fila
    total_columnas = max_col + 1
    mostrar_filas = min(total_filas, MAX_FILAS)
    mostrar_cols = min(total_columnas, MAX_COLUMNAS)
    if total_filas > MAX_FILAS or total_columnas > MAX_COLUMNAS:
        truncada = True

    filas = []
    for n in range(1, mostrar_filas + 1):
        fila_celdas = celdas.get(n, {})
        filas.append([fila_celdas.get(col, ('', False)) for col in range(mostrar_cols)])
    return {
        'nombre': nombre,
        'filas': filas,
        'columnas': mostrar_cols,
        'letras': [nombre_columna(i) for i in range(mostrar_cols)],
        'total_filas': total_filas,
        'total_columnas': total_columnas,
        'truncada': truncada,
    }


def nombre_columna(indice):
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    texto = ''
    n = indice + 1
    while n:
        n, resto = divmod(n - 1, 26)
        texto = chr(65 + resto) + texto
    return texto


def leer_xlsx(archivo):
    """Lee un .xlsx (objeto tipo archivo) y devuelve la lista de hojas."""
    try:
        zf = zipfile.ZipFile(archivo)
    except (zipfile.BadZipFile, OSError):
        raise ErrorExcel("El archivo no es un libro de Excel (.xlsx) válido.")

    with zf:
        if sum(i.file_size for i in zf.infolist()) > MAX_BYTES_TOTAL:
            raise ErrorExcel("El archivo es demasiado grande para leerlo aquí.")

        libro = _parsear(_leer_parte(zf, 'xl/workbook.xml', obligatoria=True))
        rels = {}
        datos_rels = _leer_parte(zf, 'xl/_rels/workbook.xml.rels')
        if datos_rels is not None:
            for rel in _parsear(datos_rels).findall(NS_PKG_REL + 'Relationship'):
                rels[rel.get('Id')] = rel.get('Target', '')

        compartidas = _cadenas_compartidas(zf)
        estilos_fecha = _estilos_fecha(zf)

        hojas = []
        contenedor = libro.find(NS + 'sheets')
        entradas = contenedor.findall(NS + 'sheet') if contenedor is not None else []
        if not entradas:
            raise ErrorExcel("El libro no tiene hojas.")
        for i, entrada in enumerate(entradas[:MAX_HOJAS], start=1):
            nombre = entrada.get('name') or f'Hoja {i}'
            destino = rels.get(entrada.get(NS_REL + 'id'), f'worksheets/sheet{i}.xml')
            ruta = destino[1:] if destino.startswith('/') else 'xl/' + destino
            datos = _leer_parte(zf, ruta)
            if datos is None:
                continue          # hoja de gráfico u otro tipo: se omite
            hojas.append(_leer_hoja(datos, compartidas, estilos_fecha, nombre))

        if not hojas:
            raise ErrorExcel("No se encontraron hojas con datos para mostrar.")
        return {'hojas': hojas, 'hojas_omitidas': max(0, len(entradas) - MAX_HOJAS)}
