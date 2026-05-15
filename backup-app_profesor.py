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

from flask import Flask, render_template, jsonify, request, Response, send_file
import json
import os
import argparse
import subprocess
from datetime import datetime
import io
import zipfile
import signal

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
except Exception:
    plt = None
    mcolors = None
    np = None

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

# Proceso del detector (si se lanza desde la web)
detector_proc = None


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
    nombre = nuevo.get("nombre", "Juego sin nombre")
    descripcion = nuevo.get("descripcion", "")
    juego = {
        "nombre": nombre,
        "descripcion": descripcion,
        "preguntas": []
    }
    datos["juegos"].append(juego)
    guardar_datos(datos)
    print(f"Juego creado: {nombre}")
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
        print(f"Pregunta creada en juego {idx}: {pregunta.get('texto', '')}")
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
    # Lanzar detector en background
    try:
        global detector_proc
        if detector_proc is not None and detector_proc.poll() is None:
            return jsonify({"ok": True, "msg": "Detector ya en ejecución"})

        # Use process group to allow termination
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        detector_proc = subprocess.Popen([os.sys.executable, "detector.py", "--alumnos", str(NUM_ALUMNOS)], **kwargs)
    except Exception as e:
        print(f"Error al lanzar detector: {e}")
    return jsonify({"ok": True})


@app.route("/api/sesion/parar", methods=["POST"])
def api_parar():
    sesion_activa["activa"] = False
    global detector_proc
    if detector_proc is not None:
        try:
            # Try graceful termination
            detector_proc.terminate()
            detector_proc.wait(timeout=2)
        except Exception:
            try:
                detector_proc.kill()
            except Exception:
                pass
        detector_proc = None
    return jsonify({"ok": True})


@app.route('/api/resultados/juego/<int:idx>')
def api_resultados_juego(idx):
    datos = cargar_datos()
    juegos = datos.get('juegos', [])
    sesiones = datos.get('sesiones', [])
    if idx < 0 or idx >= len(juegos):
        return jsonify({'error': 'Juego no encontrado'}), 404

    juego = juegos[idx]
    preguntas = juego.get('preguntas', [])
    total_students = NUM_ALUMNOS

    resultados = []
    # Para cada pregunta, buscar la última sesión guardada de ese juego+pregunta
    for qidx, pregunta in enumerate(preguntas):
        last = None
        for s in reversed(sesiones):
            sj = s.get('juego', {})
            sp = s.get('pregunta', {})
            if sj.get('id') == idx and sp.get('pregunta_idx') == qidx:
                last = s
                break

        conteo = { 'A': 0, 'B': 0, 'C': 0, 'D': 0 }
        total_respuestas = 0
        alumnos = {}
        respuestas = {}
        if last:
            respuestas = last.get('respuestas', {})
            alumnos = last.get('alumnos', {})
            for v in respuestas.values():
                if v in conteo:
                    conteo[v] += 1
                    total_respuestas += 1

        porcentajes = {}
        for k in ['A','B','C','D']:
            # porcentaje respecto al total de alumnos configurados
            pct = (conteo[k] / total_students) * 100 if total_students > 0 else 0
            porcentajes[k] = round(pct, 1)

        resultados.append({
            'pregunta_idx': qidx,
            'texto': pregunta.get('texto'),
            'conteo': conteo,
            'porcentajes': porcentajes,
            'total_respuestas': total_respuestas,
            'last_session': last,
        })

    return jsonify({'juego': {'id': idx, 'nombre': juego.get('nombre')}, 'resultados': resultados})


@app.route('/api/resultados/clear', methods=['POST'])
def api_resultados_clear():
    datos = cargar_datos()
    sesiones = datos.get('sesiones', [])
    data = request.json or {}
    game = data.get('game')
    removed = 0
    if game is None:
        removed = len(sesiones)
        datos['sesiones'] = []
    else:
        nuevas = [s for s in sesiones if s.get('juego', {}).get('id') != int(game)]
        removed = len(sesiones) - len(nuevas)
        datos['sesiones'] = nuevas
    guardar_datos(datos)
    return jsonify({'ok': True, 'removed': removed})


@app.route('/api/resultados/export')
def api_resultados_export():
    if plt is None or np is None:
        return jsonify({'error': 'matplotlib o numpy no disponible. Instala las dependencias en el entorno.'}), 500

    game = request.args.get('game')
    if game is None:
        return jsonify({'error': 'Parámetro game requerido'}), 400
    try:
        game = int(game)
    except Exception:
        return jsonify({'error': 'Parámetro game inválido'}), 400

    datos = cargar_datos()
    juegos = datos.get('juegos', [])
    sesiones = [s for s in datos.get('sesiones', []) if s.get('juego', {}).get('id') == game]
    if game < 0 or game >= len(juegos):
        return jsonify({'error': 'Juego no encontrado'}), 404

    juego = juegos[game]
    preguntas = juego.get('preguntas', [])

    n_q = len(preguntas)
    n_s = NUM_ALUMNOS

    # Construir matriz (n_s x n_q) con códigos: A=0,B=1,C=2,D=3, MISSING=4
    code_map = {'A':0,'B':1,'C':2,'D':3}
    mat = np.full((n_s, n_q), 4, dtype=int)

    for qidx in range(n_q):
        last = None
        for s in reversed(sesiones):
            sp = s.get('pregunta', {})
            if sp.get('pregunta_idx') == qidx:
                last = s
                break
        if last:
            resp = last.get('respuestas', {})
            for sid, letter in resp.items():
                try:
                    i = int(sid)
                    if 0 <= i < n_s and letter in code_map:
                        mat[i, qidx] = code_map[letter]
                except Exception:
                    continue

    # Crear figura heatmap
    colors = ['#E74C3C','#3498DB','#2ECC71','#F39C12','#2b2b2b']
    cmap = mcolors.ListedColormap(colors)

    fig, ax = plt.subplots(figsize=(max(6, n_q*0.8), max(6, n_s*0.12)))
    im = ax.imshow(mat, cmap=cmap, aspect='auto', vmin=0, vmax=4)
    ax.set_xlabel('Preguntas')
    ax.set_ylabel('Alumnos')
    ax.set_xticks(range(n_q))
    ax.set_xticklabels([str(i+1) for i in range(n_q)])
    ax.set_yticks(range(n_s))
    datos_global = cargar_datos()
    alumnos_global = datos_global.get('alumnos', {})
    y_labels = [alumnos_global.get(str(i), {}).get('nombre', f'Alumno {i}') for i in range(n_s)]
    ax.set_yticklabels(y_labels)
    cbar = fig.colorbar(im, ax=ax, ticks=[0,1,2,3,4])
    cbar.ax.set_yticklabels(['A','B','C','D','-'])
    ax.set_title(f"{juego.get('nombre','Juego')} - Respuestas por alumno (última por pregunta)")
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)

    # CSV
    import csv
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    header = ['Alumno'] + [f'P{q+1}' for q in range(n_q)]
    writer.writerow(header)
    for i in range(n_s):
        row = [alumnos_global.get(str(i), {}).get('nombre', f'Alumno {i}')]
        for q in range(n_q):
            val = mat[i, q]
            if val == 4:
                row.append('')
            else:
                row.append(['A','B','C','D'][int(val)])
        writer.writerow(row)
    csv_bytes = csv_buf.getvalue().encode('utf-8')

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w') as z:
        z.writestr('respuestas_por_alumno.png', buf.read())
        z.writestr('respuestas.csv', csv_bytes)
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True, download_name=f'resultados_juego_{game}.zip')


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

    # Asegurar que el juego tenga un id entero si viene en la petición
    try:
        juego_id = int(juego.get('id'))
    except Exception:
        juego_id = juego.get('id') if isinstance(juego.get('id'), int) else None
    if juego_id is not None:
        juego['id'] = juego_id

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
    print(f"Sesión guardada: {len(respuestas)} respuestas")
    return jsonify({"ok": True})


@app.route("/api/sesion/respuestas", methods=["POST"])
def api_recibir_respuestas():
    if sesion_activa["activa"]:
        nuevas = request.json.get("respuestas", {})
        sesion_activa["respuestas"].update(nuevas)
    return jsonify({"ok": True})


@app.route("/api/sesiones")
def api_sesiones():
    datos = cargar_datos()
    sesiones = datos.get("sesiones", [])
    # Incluir nombres de alumnos en cada sesión
    alumnos = datos.get("alumnos", {})
    for sesion in sesiones:
        sesion["alumnos"] = alumnos
    return jsonify(sesiones)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyLickers - Interfaz del Profesor")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--alumnos", type=int, default=30)
    args = parser.parse_args()
    NUM_ALUMNOS = min(max(args.alumnos, 1), 49)

    print(f"PyLickers Web arrancando en http://localhost:{args.port}")
    print(f"Alumnos configurados: {NUM_ALUMNOS}")
    app.run(host="0.0.0.0", port=args.port, debug=True)
