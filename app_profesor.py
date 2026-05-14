#!/usr/bin/env python3
"""
PyLickers - INTERFAZ WEB DEL PROFESOR
======================================
Aplicación Flask que proporciona:
- Gestión de juegos y preguntas
- Gestión de alumnos con import/export
- Vista de resultados en tiempo real
- API para comunicarse con el detector

Uso:
    python app_profesor.py              # Arrancar en http://localhost:5000
    python app_profesor.py --port 8080  # Puerto personalizado
    python app_profesor.py --alumnos 25  # Número máximo de alumnos (1-49)

Requisitos:
    pip install flask
"""

from flask import Flask, render_template, jsonify, request, Response
import json
import os
import argparse
from datetime import datetime

app = Flask(__name__)

# ── Configuración ────────────────────────────────
NUM_ALUMNOS = 30  # Número máximo de alumnos, configurable por argumento
DATA_FILE = "pylickers_data.json"


def cargar_datos():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            datos = json.load(f)
    else:
        datos = {}

    datos.setdefault("preguntas", [])
    datos.setdefault("sesiones", [])
    datos.setdefault("alumnos", {})
    datos.setdefault("juegos", [{"nombre": "General", "descripcion": "Juego general", "preguntas": []}])
    return datos


def guardar_datos(datos):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


# ── Estado global de la sesión activa ────────────────────────────
sesion_activa = {
    "pregunta_actual": None,
    "respuestas": {},
    "activa": False,
}


# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("app_profesor.html", num_alumnos=NUM_ALUMNOS)


@app.route("/api/juegos", methods=["GET"])
def api_juegos():
    datos = cargar_datos()
    return jsonify(datos["juegos"])


@app.route("/api/juegos", methods=["POST"])
def api_crear_juego():
    datos = cargar_datos()
    nuevo = request.json or {}
    juego = {
        "nombre": nuevo.get("nombre", "Juego sin nombre"),
        "descripcion": nuevo.get("descripcion", ""),
        "preguntas": []
    }
    datos["juegos"].append(juego)
    guardar_datos(datos)
    return jsonify({"ok": True, "id": len(datos["juegos"]) - 1})


@app.route("/api/juegos/<int:idx>/preguntas", methods=["GET"])
def api_preguntas_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        return jsonify(juegos[idx].get("preguntas", []))
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/juegos/<int:idx>/preguntas", methods=["POST"])
def api_crear_pregunta_en_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        pregunta = request.json or {}
        juegos[idx].setdefault("preguntas", []).append(pregunta)
        guardar_datos(datos)
        return jsonify({"ok": True})
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/alumnos", methods=["GET"])
def api_alumnos():
    datos = cargar_datos()
    return jsonify(datos.get("alumnos", {}))


@app.route("/api/alumnos/asignar-nombre", methods=["POST"])
def api_asignar_nombre():
    datos = cargar_datos()
    data = request.json or {}
    id_alumno = data.get("id")
    nombre = (data.get("nombre") or "").strip()
    if id_alumno is None or not isinstance(id_alumno, int):
        return jsonify({"error": "ID de alumno inválido"}), 400
    datos.setdefault("alumnos", {})
    datos["alumnos"][str(id_alumno)] = {"nombre": nombre}
    guardar_datos(datos)
    return jsonify({"ok": True})


@app.route("/api/alumnos/reset", methods=["POST"])
def api_reset_alumnos():
    datos = cargar_datos()
    datos["alumnos"] = {}
    guardar_datos(datos)
    return jsonify({"ok": True})


@app.route("/api/alumnos/importar", methods=["POST"])
def api_importar_alumnos():
    datos = cargar_datos()
    if "file" not in request.files:
        return jsonify({"error": "No se encontró el archivo"}), 400
    archivo = request.files["file"]
    if archivo.filename == "":
        return jsonify({"error": "Archivo vacío"}), 400
    if not archivo.filename.lower().endswith(".txt"):
        return jsonify({"error": "Solo archivos .txt"}), 400
    max_alumnos = min(max(int(request.args.get("max", NUM_ALUMNOS)), 1), 49)
    try:
        content = archivo.read().decode("utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        datos.setdefault("alumnos", {})
        imported = 0
        for i, nombre in enumerate(lines[:max_alumnos]):
            datos["alumnos"][str(i)] = {"nombre": nombre}
            imported += 1
        guardar_datos(datos)
        return jsonify({"imported": imported})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/alumnos/exportar", methods=["GET"])
def api_exportar_alumnos():
    datos = cargar_datos()
    alumnos = datos.get("alumnos", {})
    max_alumnos = min(max(int(request.args.get("max", NUM_ALUMNOS)), 1), 49)
    output = []
    for i in range(max_alumnos):
        output.append(alumnos.get(str(i), {}).get("nombre", ""))
    response = Response("\n".join(output), mimetype="text/plain")
    response.headers["Content-Disposition"] = "attachment; filename=alumnos.txt"
    return response


# ── API de sesión (el detector envía datos aquí) ───
@app.route("/api/sesion/estado")
def api_estado():
    return jsonify(sesion_activa)


@app.route("/api/sesion/iniciar", methods=["POST"])
def api_iniciar():
    sesion_activa["activa"] = True
    return jsonify({"ok": True})


@app.route("/api/sesion/parar", methods=["POST"])
def api_parar():
    sesion_activa["activa"] = False
    return jsonify({"ok": True})


@app.route("/api/sesion/reset", methods=["POST"])
def api_reset():
    sesion_activa["respuestas"] = {}
    sesion_activa["pregunta_actual"] = None
    return jsonify({"ok": True})

@app.route("/api/sesion/pregunta", methods=["POST"])
def api_actualizar_pregunta():
    data = request.json or {}
    juego_idx = data.get("juego_idx")
    pregunta_idx = data.get("pregunta_idx")
    pregunta = data.get("pregunta", {})
    if not isinstance(juego_idx, int) or not isinstance(pregunta_idx, int):
        return jsonify({"error": "Juego o pregunta inválidos"}), 400
    sesion_activa["pregunta_actual"] = {
        "juego_idx": juego_idx,
        "pregunta_idx": pregunta_idx,
        "pregunta": pregunta,
    }
    return jsonify({"ok": True})

@app.route("/api/sesion/guardar", methods=["POST"])
def api_guardar_sesion():
    datos = cargar_datos()
    payload = request.json or {}
    respuestas = payload.get("respuestas", {})
    pregunta = payload.get("pregunta", {})
    juego = payload.get("juego", {})
    alumnos = payload.get("alumnos", {})

    registro = {
        "timestamp": datetime.now().isoformat(),
        "juego": juego,
        "pregunta": pregunta,
        "respuestas": respuestas,
        "alumnos": alumnos,
        "total_respuestas": len(respuestas),
    }
    datos.setdefault("sesiones", []).append(registro)
    guardar_datos(datos)
    return jsonify({"ok": True})


@app.route("/api/sesion/respuestas", methods=["POST"])
def api_recibir_respuestas():
    if sesion_activa["activa"]:
        nuevas = request.json.get("respuestas", {})
        sesion_activa["respuestas"].update(nuevas)
    return jsonify({"ok": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyLickers - Interfaz del Profesor")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--alumnos", type=int, default=30)
    args = parser.parse_args()
    NUM_ALUMNOS = min(max(args.alumnos, 1), 49)

    print(f"PyLickers Web arrancando en http://localhost:{args.port}")
    print(f"Alumnos configurados: {NUM_ALUMNOS}")
    app.run(host="0.0.0.0", port=args.port, debug=True)
