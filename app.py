from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

DATA_FILE = os.path.join(os.getcwd(), "datos_realtime.jsonl")


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

    total = contar_registros()

    return jsonify({
        "mensaje": "Datos recibidos correctamente",
        "archivo": DATA_FILE,
        "total_registros": total,
        "data": data
    }), 200


@app.route("/ver-datos", methods=["GET"])
def ver_datos():
    datos = []

    print("LEYENDO DESDE:", DATA_FILE, flush=True)

    if not os.path.exists(DATA_FILE):
        return jsonify({
            "mensaje": "Aún no hay datos recibidos",
            "archivo": DATA_FILE,
            "datos": []
        }), 200

    with open(DATA_FILE, "r", encoding="utf-8") as archivo:
        for linea in archivo:
            datos.append(json.loads(linea))

    return jsonify({
        "mensaje": "Datos encontrados",
        "archivo": DATA_FILE,
        "total_registros": len(datos),
        "datos": datos
    }), 200


@app.route("/debug", methods=["GET"])
def debug():
    return jsonify({
        "cwd": os.getcwd(),
        "archivo": DATA_FILE,
        "existe_archivo": os.path.exists(DATA_FILE)
    })


def contar_registros():
    if not os.path.exists(DATA_FILE):
        return 0

    with open(DATA_FILE, "r", encoding="utf-8") as archivo:
        return sum(1 for _ in archivo)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)