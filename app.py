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


@app.route("/", methods=["GET"])
def inicio():
    return "API funcionando correctamente"


@app.route("/recibir-datos", methods=["POST"])
def recibir_datos():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            "mensaje": "No se recibió JSON válido"
        }), 400

    registro = {
        "fecha_recepcion": datetime.now().isoformat(),
        "data": data
    }

    print("POST RECIBIDO:", registro, flush=True)
    print("GUARDANDO EN:", DATA_FILE, flush=True)

    with open(DATA_FILE, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return jsonify({
        "mensaje": "Datos recibidos correctamente",
        "archivo": DATA_FILE,
        "total_registros_crudos": contar_registros_crudos(),
        "data": data
    }), 200


@app.route("/ver-datos", methods=["GET"])
def ver_datos():
    datos = leer_registros_crudos()

    return jsonify({
        "mensaje": "Datos encontrados" if datos else "Aún no hay datos recibidos",
        "archivo": DATA_FILE,
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
            "Content-Disposition": "attachment; filename=datos_realtime_limpios.csv"
        }
    )


@app.route("/resumen", methods=["GET"])
def resumen():
    filas = obtener_datos_limpios()

    total_monto = sum(fila["monto"] for fila in filas if isinstance(fila["monto"], (int, float)))
    total_cantidad = sum(fila["cantidad"] for fila in filas if isinstance(fila["cantidad"], int))

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
    })


@app.route("/debug", methods=["GET"])
def debug():
    return jsonify({
        "cwd": os.getcwd(),
        "archivo": DATA_FILE,
        "existe_archivo": os.path.exists(DATA_FILE)
    })


def leer_registros_crudos():
    if not os.path.exists(DATA_FILE):
        return []

    datos = []

    with open(DATA_FILE, "r", encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue

            try:
                datos.append(json.loads(linea))
            except json.JSONDecodeError:
                print("Línea inválida ignorada:", linea, flush=True)

    return datos


def contar_registros_crudos():
    return len(leer_registros_crudos())


def obtener_datos_limpios():
    registros = leer_registros_crudos()
    filas = []
    duplicados = set()

    for registro in registros:
        fecha_recepcion = registro.get("fecha_recepcion", "")
        data = registro.get("data", [])

        # Duoc a veces manda una lista de ventas.
        # La prueba manual de PowerShell manda solo un diccionario.
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            fila = transformar_item(item, fecha_recepcion)

            clave_duplicado = crear_clave_duplicado(fila)

            if clave_duplicado in duplicados:
                continue

            duplicados.add(clave_duplicado)
            filas.append(fila)

    filas.sort(key=lambda x: x["fecha_registro"] or x["fecha_recepcion_api"])

    return filas


def transformar_item(item, fecha_recepcion):
    precio = convertir_float(item.get("precio"))
    cantidad = convertir_int(item.get("cantidad"))
    monto = convertir_float(item.get("monto"))

    # Enriquecimiento: si no viene monto, lo calculamos.
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

    return json.dumps(campos_clave, sort_keys=True, ensure_ascii=False)


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

        # Soporta formato 1.234,56 y también 1234.56
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
        return int(float(str(valor).strip().replace(",", ".")))
    except ValueError:
        return None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)