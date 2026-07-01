from flask import Flask, request, jsonify, Response
from datetime import datetime
import json
import os
import csv
from io import StringIO

app = Flask(__name__)

DATA_FILE = os.path.join(os.getcwd(), "datos_realtime.jsonl")

COLUMNAS_CSV = [
    "fecha_recepcion_api",
    "fecha_registro",
    "id_cliente",
    "cliente",
    "genero",
    "id_producto",
    "producto",
    "precio",
    "cantidad",
    "monto",
    "forma_pago",
    "estado_validacion",
    "observaciones"
]

# Campos que permiten reconocer que un diccionario corresponde
# a un evento/venta válido para el proceso.
CAMPOS_REFERENCIA_EVENTO = {
    "cantidad",
    "cliente",
    "fecreg",
    "forma_pago",
    "genero",
    "id_cliente",
    "id_producto",
    "monto",
    "precio",
    "producto"
}


@app.route("/", methods=["GET"])
def inicio():
    return "API funcionando correctamente", 200


@app.route("/recibir-datos", methods=["POST"])
def recibir_datos():
    # Lee el cuerpo tal como llegó, sin depender de Thunder Client
    # ni del Content-Type configurado.
    cuerpo = request.get_data(as_text=True)

    if not cuerpo or not cuerpo.strip():
        return jsonify({
            "estado": "rechazado",
            "error": "Cuerpo vacío",
            "detalle": "La solicitud no contiene datos para procesar."
        }), 400

    # Valida que el contenido sea JSON real.
    try:
        payload = json.loads(cuerpo)
    except json.JSONDecodeError:
        return jsonify({
            "estado": "rechazado",
            "error": "JSON inválido",
            "detalle": "El cuerpo enviado no tiene una estructura JSON válida."
        }), 400

    # Acepta tres formatos:
    # 1. Lista de eventos: [{...}, {...}]
    # 2. Objeto con data: {"data": [{...}]}
    # 3. Un único evento: {...}
    eventos, error_estructura = extraer_eventos_entrada(payload)

    if error_estructura:
        return jsonify({
            "estado": "rechazado",
            "error": "Estructura inválida",
            "detalle": error_estructura
        }), 400

    fecha_recepcion = datetime.now().astimezone().isoformat()

    # Se almacena siempre una lista de eventos, aunque llegue uno solo.
    registro = {
        "fecha_recepcion": fecha_recepcion,
        "data": eventos
    }

    print(
        f"POST recibido: {len(eventos)} evento(s) - {fecha_recepcion}",
        flush=True
    )

    try:
        with open(DATA_FILE, "a", encoding="utf-8") as archivo:
            archivo.write(
                json.dumps(registro, ensure_ascii=False) + "\n"
            )
    except OSError as error:
        print("Error al guardar:", error, flush=True)

        return jsonify({
            "estado": "error",
            "error": "No fue posible guardar los datos."
        }), 500

    return jsonify({
        "estado": "recibido",
        "mensaje": "Datos recibidos correctamente",
        "fecha_recepcion": fecha_recepcion,
        "registros_recibidos": len(eventos),
        "lotes_crudos_acumulados": contar_registros_crudos()
    }), 200


@app.route("/ver-datos", methods=["GET"])
def ver_datos():
    datos = leer_registros_crudos()

    return jsonify({
        "mensaje": "Datos encontrados" if datos else "Aún no hay datos recibidos",
        "archivo_origen": os.path.basename(DATA_FILE),
        "total_registros_crudos": len(datos),
        "datos": datos
    }), 200


@app.route("/datos-limpios", methods=["GET"])
def datos_limpios():
    filas = obtener_datos_limpios()

    return jsonify({
        "mensaje": "Datos limpios generados correctamente",
        "total_registros_limpios": len(filas),
        "datos": filas
    }), 200


@app.route("/descargar-csv", methods=["GET"])
def descargar_csv():
    filas = obtener_datos_limpios()

    salida = StringIO()
    writer = csv.DictWriter(salida, fieldnames=COLUMNAS_CSV)

    writer.writeheader()
    writer.writerows(filas)

    csv_texto = salida.getvalue()

    return Response(
        csv_texto,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=datos_realtime_limpios.csv"
            )
        }
    )


@app.route("/resumen", methods=["GET"])
def resumen():
    filas = obtener_datos_limpios()

    total_monto = sum(
        fila["monto"]
        for fila in filas
        if isinstance(fila["monto"], (int, float))
    )

    total_cantidad = sum(
        fila["cantidad"]
        for fila in filas
        if isinstance(fila["cantidad"], int)
    )

    productos = {}
    formas_pago = {}

    for fila in filas:
        producto = fila["producto"] or "Sin producto"
        forma_pago = fila["forma_pago"] or "Sin forma de pago"

        productos[producto] = productos.get(producto, 0) + 1
        formas_pago[forma_pago] = formas_pago.get(forma_pago, 0) + 1

    return jsonify({
        "total_registros_limpios": len(filas),
        "total_cantidad": total_cantidad,
        "total_monto": round(total_monto, 2),
        "productos": productos,
        "formas_pago": formas_pago
    }), 200


def extraer_eventos_entrada(payload):
    """
    Convierte el payload recibido en una lista de eventos.
    Retorna: (eventos, mensaje_error)
    """

    if isinstance(payload, list):
        eventos = payload

    elif isinstance(payload, dict):
        # Caso: {"data": [{...}, {...}]}
        if "data" in payload:
            contenido = payload["data"]

            if isinstance(contenido, list):
                eventos = contenido

            elif isinstance(contenido, dict):
                eventos = [contenido]

            else:
                return None, (
                    "La clave 'data' debe contener un objeto o una lista de registros."
                )

        # Caso: un único evento directo: {"cliente": "...", ...}
        elif es_evento_estructura_valida(payload):
            eventos = [payload]

        else:
            return None, (
                "Se esperaba una lista de eventos, un objeto con la clave "
                "'data' o un evento con campos como cliente, producto o monto."
            )

    else:
        return None, (
            "El JSON debe ser una lista o un objeto."
        )

    if not eventos:
        return None, "No se recibieron eventos para procesar."

    for indice, evento in enumerate(eventos, start=1):
        if not isinstance(evento, dict):
            return None, (
                f"El registro {indice} no tiene formato de objeto JSON."
            )

        if not es_evento_estructura_valida(evento):
            return None, (
                f"El registro {indice} no contiene campos propios de una venta o evento."
            )

    return eventos, None


def es_evento_estructura_valida(item):
    if not isinstance(item, dict):
        return False

    return any(
        campo in item
        for campo in CAMPOS_REFERENCIA_EVENTO
    )


def leer_registros_crudos():
    if not os.path.exists(DATA_FILE):
        return []

    datos = []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                linea = linea.strip()

                if not linea:
                    continue

                try:
                    datos.append(json.loads(linea))
                except json.JSONDecodeError:
                    print(
                        "Línea inválida ignorada en datos_realtime.jsonl",
                        flush=True
                    )

    except OSError as error:
        print("Error al leer archivo:", error, flush=True)

    return datos


def contar_registros_crudos():
    return len(leer_registros_crudos())


def normalizar_items_almacenados(data):
    """
    Permite leer tanto los registros nuevos como registros antiguos
    generados antes de esta mejora.
    """

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Compatibilidad con datos que podrían haber llegado
        # como {"data": [{...}]}
        if "data" in data:
            contenido = data.get("data")

            if isinstance(contenido, list):
                return contenido

            if isinstance(contenido, dict):
                return [contenido]

        return [data]

    return []


def obtener_datos_limpios():
    registros = leer_registros_crudos()
    filas = []
    duplicados = set()

    for registro in registros:
        fecha_recepcion = registro.get("fecha_recepcion", "")
        data = registro.get("data", [])

        items = normalizar_items_almacenados(data)

        for item in items:
            # Ignora pruebas antiguas mal enviadas o estructuras
            # que no correspondan a ventas reales.
            if not es_evento_estructura_valida(item):
                continue

            fila = transformar_item(item, fecha_recepcion)

            clave_duplicado = crear_clave_duplicado(fila)

            if clave_duplicado in duplicados:
                continue

            duplicados.add(clave_duplicado)
            filas.append(fila)

    filas.sort(
        key=lambda fila: (
            fila["fecha_registro"] or fila["fecha_recepcion_api"]
        )
    )

    return filas


def transformar_item(item, fecha_recepcion):
    precio = convertir_float(item.get("precio"))
    cantidad = convertir_int(item.get("cantidad"))
    monto = convertir_float(item.get("monto"))

    # Enriquecimiento: si no viene monto, se calcula.
    if monto is None and precio is not None and cantidad is not None:
        monto = round(precio * cantidad, 2)

    producto = limpiar_texto(item.get("producto"))
    cliente = limpiar_texto(item.get("cliente"))
    forma_pago = limpiar_texto(item.get("forma_pago"))
    genero = limpiar_texto(item.get("genero"))

    observaciones = []

    if not producto:
        observaciones.append("Producto vacío")

    if precio is None:
        observaciones.append("Precio inválido o vacío")

    if cantidad is None:
        observaciones.append("Cantidad inválida o vacía")

    estado_validacion = "OK" if not observaciones else "OBSERVADO"

    return {
        "fecha_recepcion_api": fecha_recepcion,
        "fecha_registro": limpiar_texto(item.get("fecreg")),
        "id_cliente": limpiar_texto(item.get("id_cliente")),
        "cliente": cliente,
        "genero": genero,
        "id_producto": limpiar_texto(item.get("id_producto")),
        "producto": producto,
        "precio": precio if precio is not None else "",
        "cantidad": cantidad if cantidad is not None else "",
        "monto": monto if monto is not None else "",
        "forma_pago": forma_pago,
        "estado_validacion": estado_validacion,
        "observaciones": "; ".join(observaciones)
    }


def crear_clave_duplicado(fila):
    campos_clave = {
        "fecha_registro": fila["fecha_registro"],
        "id_cliente": fila["id_cliente"],
        "cliente": fila["cliente"],
        "id_producto": fila["id_producto"],
        "producto": fila["producto"],
        "precio": fila["precio"],
        "cantidad": fila["cantidad"],
        "monto": fila["monto"],
        "forma_pago": fila["forma_pago"]
    }

    return json.dumps(
        campos_clave,
        sort_keys=True,
        ensure_ascii=False
    )


def limpiar_texto(valor):
    if valor is None:
        return ""

    return str(valor).strip()


def convertir_float(valor):
    if valor is None or valor == "":
        return None

    try:
        texto = str(valor).strip()
        texto = texto.replace("$", "").replace(" ", "")

        # Soporta 1.234,56 y 1234.56
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")

        return float(texto)

    except ValueError:
        return None


def convertir_int(valor):
    if valor is None or valor == "":
        return None

    try:
        return int(
            float(
                str(valor).strip().replace(",", ".")
            )
        )

    except ValueError:
        return None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)