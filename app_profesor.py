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
import sys
import argparse
import subprocess
from datetime import datetime
import io
import csv
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
DETECTOR_KEEP_RUNNING = True


def cargar_datos():
    datos = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            backup_file = DATA_FILE + ".corrupt.bak"
            try:
                os.replace(DATA_FILE, backup_file)
            except Exception:
                backup_file = None
            print(f"Advertencia: {DATA_FILE} corrupto y no pudo cargarse. Se usará un archivo nuevo.{'' if not backup_file else ' Backup:' + backup_file}")
            datos = {}
        except Exception as exc:
            print(f"Error leyéndo {DATA_FILE}: {exc}")
            datos = {}

    datos.setdefault("preguntas", [])
    datos.setdefault("sesiones", [])
    if "partidas" not in datos:
        datos["partidas"] = datos["sesiones"]
    else:
        datos.setdefault("partidas", [])
    if "sesiones" not in datos:
        datos["sesiones"] = datos["partidas"]
    datos.setdefault("alumnos", {})
    datos.setdefault("juegos", [{"nombre": "General", "descripcion": "Juego general", "preguntas": []}])
    if not datos["juegos"]:
        datos["juegos"] = [{"nombre": "General", "descripcion": "Juego general", "preguntas": []}]

    if not os.path.exists(DATA_FILE) or (isinstance(datos, dict) and not datos):
        guardar_datos(datos)

    return datos


def guardar_datos(datos):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


# ── Estado global de la sesión activa ────────────────────────────
sesion_activa = {
    "pregunta_actual": None,
    "respuestas": {},
    "activa": False,
    "juego_en_progreso": None,  # Información del juego actual
    "respuestas_por_pregunta": {},  # {pregunta_idx: {alumno_id: respuesta}}
    "juego_iniciado": False,  # Indica si está en modo juego
    "reset_counter": 0,  # Incrementar para indicar al detector que debe resetear
    "reset_scheduled": False,  # Cuando True, indica que un reset fue solicitado (por detector)
    "pausing": False,  # Cuando True, bufferizar incoming respuestas temporalmente
    "incoming_buffer": [],  # Lista de dicts con respuestas recibidas durante la pausa
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


@app.route("/api/juegos/<int:idx>", methods=["PUT"])
def api_actualizar_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        data = request.json or {}
        juegos[idx]["nombre"] = data.get("nombre", juegos[idx].get("nombre", "Juego sin nombre"))
        juegos[idx]["descripcion"] = data.get("descripcion", juegos[idx].get("descripcion", ""))
        guardar_datos(datos)
        return jsonify({"ok": True})
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/juegos/<int:idx>", methods=["DELETE"])
def api_borrar_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        juegos.pop(idx)
        guardar_datos(datos)
        return jsonify({"ok": True})
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/juegos/<int:idx>/preguntas", methods=["GET"])
def api_preguntas_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        return jsonify(juegos[idx].get("preguntas", []))
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/juegos/<int:idx>/preguntas", methods=["PUT"])
def api_actualizar_preguntas_juego(idx):
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        preguntas = request.json.get("preguntas") if request.json else None
        if isinstance(preguntas, list):
            juegos[idx]["preguntas"] = preguntas
            guardar_datos(datos)
            return jsonify({"ok": True})
        return jsonify({"error": "Preguntas inválidas"}), 400
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


@app.route("/api/juegos/<int:idx>/preguntas/<int:pregunta_idx>", methods=["PUT"])
def api_editar_pregunta_en_juego(idx, pregunta_idx):
    """Edita una pregunta existente en un juego."""
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        preguntas = juegos[idx].get("preguntas", [])
        if 0 <= pregunta_idx < len(preguntas):
            pregunta_actualizada = request.json or {}
            preguntas[pregunta_idx] = pregunta_actualizada
            guardar_datos(datos)
            print(f"Pregunta editada en juego {idx}, índice {pregunta_idx}")
            return jsonify({"ok": True})
        return jsonify({"error": "Pregunta no encontrada"}), 404
    return jsonify({"error": "Juego no encontrado"}), 404


@app.route("/api/juegos/<int:idx>/preguntas/<int:pregunta_idx>", methods=["DELETE"])
def api_eliminar_pregunta_en_juego(idx, pregunta_idx):
    """Elimina una pregunta de un juego."""
    datos = cargar_datos()
    juegos = datos["juegos"]
    if 0 <= idx < len(juegos):
        preguntas = juegos[idx].get("preguntas", [])
        if 0 <= pregunta_idx < len(preguntas):
            preguntas.pop(pregunta_idx)
            guardar_datos(datos)
            print(f"Pregunta eliminada en juego {idx}, índice {pregunta_idx}")
            return jsonify({"ok": True})
        return jsonify({"error": "Pregunta no encontrada"}), 404
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
            return jsonify({"ok": True, "msg": "Detector ya en ejecución", "pid": detector_proc.pid})

        # Use process group to allow termination
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        detector_proc = subprocess.Popen([sys.executable, "detector.py", "--alumnos", str(NUM_ALUMNOS)], **kwargs)
        return jsonify({"ok": True, "pid": detector_proc.pid})
    except Exception as e:
        print(f"Error al lanzar detector: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sesion/parar", methods=["POST"])
def api_parar():
    sesion_activa["activa"] = False
    global detector_proc
    if detector_proc is None or detector_proc.poll() is not None:
        detector_proc = None
        return jsonify({"ok": True, "msg": "No había proceso del detector"})

    if DETECTOR_KEEP_RUNNING:
        return jsonify({"ok": True, "msg": "Sesión detenida. El detector permanece listo para el siguiente inicio."})

    try:
        # Try graceful termination
        if os.name == 'nt':
            try:
                # send CTRL_BREAK to the process group
                detector_proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                detector_proc.terminate()
        else:
            detector_proc.terminate()
        detector_proc.wait(timeout=3)
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
    partidas = datos.get('partidas', [])
    if idx < 0 or idx >= len(juegos):
        return jsonify({'error': 'Juego no encontrado'}), 404

    juego = juegos[idx]
    preguntas = juego.get('preguntas', [])
    total_students = NUM_ALUMNOS

    resultados = []
    # Para cada pregunta, buscar la última partida guardada de ese juego+pregunta
    for qidx, pregunta in enumerate(preguntas):
        last = None
        for s in reversed(partidas):
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
    partidas = datos.get('partidas', [])
    data = request.json or {}
    game = data.get('game')
    removed = 0
    if game is None:
        removed = len(partidas)
        datos['partidas'] = []
        datos['sesiones'] = []
    else:
        nuevas = [p for p in partidas if p.get('juego', {}).get('id') != int(game)]
        removed = len(partidas) - len(nuevas)
        datos['partidas'] = nuevas
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
    partidas = [p for p in datos.get('partidas', []) if p.get('juego', {}).get('id') == game]
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
        for s in reversed(partidas):
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
        row = [alumnos_global.get(str(i), {}).get('nombre', f'Alumno {i+1}')]
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
        "partida_id": len(datos.get("partidas", [])),
        "timestamp": datetime.now().isoformat(),
        "juego": juego,
        "pregunta": pregunta,
        "respuestas": respuestas,
        "alumnos": alumnos,
        "total_respuestas": len(respuestas),
    }
    datos.setdefault("partidas", []).append(registro)
    datos.setdefault("sesiones", datos["partidas"])
    guardar_datos(datos)
    print(f"Partida guardada: {len(respuestas)} respuestas")
    return jsonify({"ok": True})


@app.route("/api/sesion/<int:session_idx>/export")
def api_exportar_sesion(session_idx):
    datos = cargar_datos()
    sesiones = datos.get("sesiones", [])
    if session_idx < 0 or session_idx >= len(sesiones):
        return jsonify({"error": "Sesión no encontrada"}), 404
    sesion = sesiones[session_idx]
    pregunta = sesion.get("pregunta", {})
    correcta = pregunta.get("correcta")
    respuestas = sesion.get("respuestas", {})
    alumnos = sesion.get("alumnos", {})

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["Alumno", "Respuesta", "Correcta", "Puntuación"])
    for i in range(NUM_ALUMNOS):
        alumno = alumnos.get(str(i), {}).get("nombre", f"Alumno {i}")
        respuesta = respuestas.get(str(i), "")
        puntaje = 0
        if respuesta:
            puntaje = 1 if respuesta == correcta else -1
        writer.writerow([alumno, respuesta, correcta, puntaje])

    output = csv_buffer.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=sesion_{session_idx}_puntaje.csv"
    return response


@app.route("/api/sesion/respuestas", methods=["POST"])
def api_recibir_respuestas():
    if not sesion_activa["activa"]:
        return jsonify({"ok": True})

    nuevas = request.json.get("respuestas", {})
    # Si estamos en pausa, bufferizar las respuestas entrantes
    if sesion_activa.get("pausing"):
        sesion_activa.setdefault("incoming_buffer", []).append(nuevas)
        return jsonify({"ok": True, "buffered": True})

    # Normal: actualizar el estado de respuestas
    sesion_activa["respuestas"].update(nuevas)
    return jsonify({"ok": True})


@app.route('/api/sesion/schedule_reset', methods=['POST'])
def api_schedule_reset():
    """Endpoint para que el detector indique que solicita un reset (programado).
    El servidor no borra inmediatamente; el reset ocurre cuando el profesor avanza la pregunta."""
    sesion_activa["reset_scheduled"] = True
    return jsonify({"ok": True})


# ── API para juego progresivo (pregunta a pregunta) ────────────────
@app.route("/api/juego/iniciar", methods=["POST"])
def api_iniciar_juego():
    """Inicia un juego completo con todas sus preguntas."""
    datos = cargar_datos()
    data = request.json or {}
    juego_idx = data.get("juego_idx")
    
    if not isinstance(juego_idx, int) or juego_idx < 0 or juego_idx >= len(datos.get("juegos", [])):
        return jsonify({"error": "Juego inválido"}), 400
    
    juego = datos["juegos"][juego_idx]
    if not juego.get("preguntas"):
        return jsonify({"error": "El juego no tiene preguntas"}), 400
    
    # Inicializar el juego en progreso
    sesion_activa["juego_en_progreso"] = {
        "juego_idx": juego_idx,
        "juego_nombre": juego.get("nombre", "Juego"),
        "pregunta_actual": 0,
        "total_preguntas": len(juego.get("preguntas", [])),
    }
    sesion_activa["respuestas_por_pregunta"] = {}
    sesion_activa["respuestas"] = {}
    # Ensure any previous buffers are cleared
    sesion_activa["incoming_buffer"] = []
    sesion_activa["pausing"] = False
    # Signal detector to reset its local state
    sesion_activa["reset_counter"] = sesion_activa.get("reset_counter", 0) + 1
    sesion_activa["reset_scheduled"] = False
    sesion_activa["juego_iniciado"] = True
    sesion_activa["activa"] = True
    
    # Iniciar escaneo
    try:
        global detector_proc
        if detector_proc is not None and detector_proc.poll() is None:
            pass
        
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        
        detector_proc = subprocess.Popen([sys.executable, "detector.py", "--alumnos", str(NUM_ALUMNOS)], **kwargs)
    except Exception as e:
        print(f"Error al lanzar detector: {e}")
        return jsonify({"error": str(e)}), 500
    
    return jsonify({
        "ok": True,
        "juego_en_progreso": sesion_activa["juego_en_progreso"],
        "pregunta": juego["preguntas"][0]
    })


@app.route("/api/juego/pregunta-siguiente", methods=["POST"])
def api_pregunta_siguiente():
    """Avanza a la siguiente pregunta y guarda las respuestas de la actual."""
    if not sesion_activa.get("juego_en_progreso"):
        return jsonify({"error": "No hay un juego en progreso"}), 400
    
    datos = cargar_datos()
    juego_en_progreso = sesion_activa["juego_en_progreso"]
    pregunta_actual = juego_en_progreso["pregunta_actual"]
    
    # Activar pausa para bufferizar entradas mientras hacemos snapshot
    sesion_activa["pausing"] = True

    # Guardar respuestas de la pregunta actual (snapshot)
    respuestas_actuales = dict(sesion_activa.get("respuestas", {}))
    if respuestas_actuales:
        sesion_activa.setdefault("respuestas_por_pregunta", {})[pregunta_actual] = respuestas_actuales

    # Reset de respuestas para la siguiente pregunta
    sesion_activa["respuestas"] = {}
    # Incrementar contador de reset para que el detector borre su acumulado
    sesion_activa["reset_counter"] = sesion_activa.get("reset_counter", 0) + 1
    sesion_activa["reset_scheduled"] = False

    # Desactivar pausa y aplicar cualquier buffer recibido durante la operación
    buffered = sesion_activa.get("incoming_buffer", []) or []
    # Merge buffered dicts into respuestas (correspond to next question)
    merged = {}
    for b in buffered:
        if isinstance(b, dict):
            merged.update(b)
    sesion_activa["incoming_buffer"] = []
    sesion_activa["pausing"] = False
    # Apply merged buffered responses to the active respuestas store
    if merged:
        sesion_activa.setdefault("respuestas", {}).update(merged)
    
    # Avanzar a la siguiente pregunta
    pregunta_actual += 1
    juego_en_progreso["pregunta_actual"] = pregunta_actual
    
    # Si llegamos al final, devolver estado de finalización
    if pregunta_actual >= juego_en_progreso["total_preguntas"]:
        return jsonify({
            "ok": True,
            "finalizado": True,
            "mensaje": "Todas las preguntas han sido respondidas"
        })
    
    # Devolver siguiente pregunta
    juego_idx = juego_en_progreso["juego_idx"]
    juego = datos["juegos"][juego_idx]
    siguiente_pregunta = juego["preguntas"][pregunta_actual]
    
    return jsonify({
        "ok": True,
        "finalizado": False,
        "pregunta_actual": pregunta_actual,
        "total_preguntas": juego_en_progreso["total_preguntas"],
        "pregunta": siguiente_pregunta
    })


@app.route("/api/juego/finalizar", methods=["POST"])
def api_finalizar_juego():
    """Finaliza el juego y guarda todas las respuestas."""
    if not sesion_activa.get("juego_en_progreso"):
        return jsonify({"error": "No hay un juego en progreso"}), 400
    
    datos = cargar_datos()
    juego_en_progreso = sesion_activa["juego_en_progreso"]
    pregunta_actual = juego_en_progreso["pregunta_actual"]
    
    # Guardar las respuestas de la última pregunta
    respuestas_actuales = sesion_activa.get("respuestas", {})
    if respuestas_actuales:
        sesion_activa["respuestas_por_pregunta"][pregunta_actual] = dict(respuestas_actuales)
    
    # Crear registro completo del juego
    juego_idx = juego_en_progreso["juego_idx"]
    juego = datos["juegos"][juego_idx]
    preguntas = juego.get("preguntas", [])
    alumnos = datos.get("alumnos", {})
    
    # Crear un registro por cada pregunta del juego
    for q_idx, pregunta in enumerate(preguntas):
        respuestas_pregunta = sesion_activa["respuestas_por_pregunta"].get(q_idx, {})
        
        registro = {
            "partida_id": len(datos.get("partidas", [])),
            "timestamp": datetime.now().isoformat(),
            "juego": {
                "id": juego_idx,
                "nombre": juego.get("nombre", "Juego"),
            },
            "pregunta": {
                "pregunta_idx": q_idx,
                "texto": pregunta.get("texto", ""),
                "correcta": pregunta.get("correcta", ""),
                "opciones": pregunta.get("opciones", {}),
            },
            "respuestas": respuestas_pregunta,
            "alumnos": alumnos,
            "total_respuestas": len(respuestas_pregunta),
        }
        datos.setdefault("partidas", []).append(registro)
    
    datos.setdefault("sesiones", datos["partidas"])
    guardar_datos(datos)
    
    # Limpiar estado del juego
    sesion_activa["juego_en_progreso"] = None
    sesion_activa["respuestas_por_pregunta"] = {}
    sesion_activa["respuestas"] = {}
    sesion_activa["reset_counter"] = sesion_activa.get("reset_counter", 0) + 1
    sesion_activa["reset_scheduled"] = False
    sesion_activa["juego_iniciado"] = False
    sesion_activa["activa"] = False
    
    # Parar escaneo
    try:
        global detector_proc
        if detector_proc is None or detector_proc.poll() is not None:
            detector_proc = None
        else:
            if os.name == 'nt':
                try:
                    os.kill(detector_proc.pid, signal.CTRL_BREAK_EVENT)
                except Exception:
                    pass
            else:
                detector_proc.terminate()
            detector_proc.wait(timeout=3)
    except Exception:
        try:
            if detector_proc:
                detector_proc.kill()
        except Exception:
            pass
    detector_proc = None
    
    print(f"Juego '{juego.get('nombre')}' finalizado. {len(preguntas)} preguntas guardadas.")
    return jsonify({"ok": True, "preguntas_guardadas": len(preguntas)})


@app.route("/api/partidas")
@app.route("/api/sesiones")
def api_partidas():
    datos = cargar_datos()
    partidas = datos.get("partidas", [])
    # Incluir nombres de alumnos en cada partida
    alumnos = datos.get("alumnos", {})
    for partida in partidas:
        partida["alumnos"] = alumnos
    return jsonify(partidas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyLickers - Interfaz del Profesor")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--alumnos", type=int, default=30)
    args = parser.parse_args()
    NUM_ALUMNOS = min(max(args.alumnos, 1), 49)

    print(f"PyLickers Web arrancando en http://localhost:{args.port}")
    print(f"Alumnos configurados: {NUM_ALUMNOS}")
    app.run(host="0.0.0.0", port=args.port, debug=True)