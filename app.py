from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def inicio():
    return "API funcionando correctamente"

@app.route("/recibir-datos", methods=["POST"])
def recibir_datos():
    data = request.get_json()

    print("POST RECIBIDO EN /recibir-datos:", data, flush=True)

    registro = {
        "fecha_recepcion": datetime.now().isoformat(),
        "data": data
    }

    with open("datos_realtime.jsonl", "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return jsonify({
        "mensaje": "Datos recibidos correctamente",
        "data": data
    }), 200

@app.route("/ver-datos", methods=["GET"])
def ver_datos():
    datos = []

    try:
        with open("datos_realtime.jsonl", "r", encoding="utf-8") as archivo:
            for linea in archivo:
                datos.append(json.loads(linea))
    except FileNotFoundError:
        return jsonify({
            "mensaje": "Aún no hay datos recibidos",
            "datos": []
        }), 200

    return jsonify({
        "total_registros": len(datos),
        "datos": datos
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)