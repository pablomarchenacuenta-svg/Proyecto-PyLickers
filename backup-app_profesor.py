#!/usr/bin/env python3
"""
PyLickers - INTERFAZ WEB DEL PROFESOR
======================================
Aplicación Flask que proporciona:
- Gestión de preguntas (crear, editar, eliminar)
- Vista de resultados en tiempo real
- Historial de sesiones
- API para comunicarse con el detector

Uso:
    python app_profesor.py              # Arrancar en http://localhost:5000
    python app_profesor.py --port 8080  # Puerto personalizado

Requisitos:
    pip install flask
"""

from flask import Flask, render_template_string, jsonify, request
import json
import os
import argparse
from datetime import datetime

app = Flask(__name__)

# ── Almacenamiento simple en JSON ────────────────────────────────
DATA_FILE = "pylickers_data.json"


def cargar_datos():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"preguntas": [], "sesiones": [], "alumnos": {}}


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
# PLANTILLA HTML (todo en un archivo para simplicidad del prototipo)
# ══════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyLickers - Panel del Profesor</title>
    <style>
        :root {
            --color-a: #E74C3C;
            --color-b: #3498DB;
            --color-c: #2ECC71;
            --color-d: #F39C12;
            --bg: #1a1a2e;
            --card-bg: #16213e;
            --text: #eee;
            --text-dim: #888;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        .header {
            background: var(--card-bg);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #0f3460;
        }
        .header h1 { font-size: 1.5rem; }
        .header h1 span { color: var(--color-b); }
        .status { display: flex; align-items: center; gap: 8px; }
        .status-dot {
            width: 12px; height: 12px; border-radius: 50%;
            background: #e74c3c;
        }
        .status-dot.active { background: #2ecc71; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

        .container { display: grid; grid-template-columns: 1fr 350px; gap: 1.5rem; padding: 1.5rem; }

        /* Panel principal */
        .main-panel { display: flex; flex-direction: column; gap: 1.5rem; }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid #0f3460;
        }
        .card h2 { margin-bottom: 1rem; font-size: 1.1rem; color: var(--color-b); }

        /* Pregunta actual */
        .question-display {
            font-size: 1.4rem;
            text-align: center;
            padding: 2rem;
            background: linear-gradient(135deg, #0f3460, #16213e);
            border-radius: 12px;
            border: 2px solid #0f3460;
        }
        .question-display .number { color: var(--text-dim); font-size: 0.9rem; }
        .options { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-top: 1.5rem; }
        .option {
            padding: 0.8rem;
            border-radius: 8px;
            font-size: 1rem;
            text-align: center;
            position: relative;
        }
        .option.a { background: var(--color-a); }
        .option.b { background: var(--color-b); }
        .option.c { background: var(--color-c); }
        .option.d { background: var(--color-d); }
        .option .count {
            position: absolute;
            top: 5px;
            right: 10px;
            background: rgba(0,0,0,0.3);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.75rem;
        }

        /* Barras de resultados */
        .results-bars { display: flex; flex-direction: column; gap: 8px; margin-top: 1rem; }
        .bar-row { display: flex; align-items: center; gap: 10px; }
        .bar-label { width: 25px; font-weight: bold; font-size: 1.1rem; }
        .bar-track { flex: 1; height: 28px; background: #0a0a1a; border-radius: 6px; overflow: hidden; }
        .bar-fill {
            height: 100%;
            border-radius: 6px;
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            padding-left: 10px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        .bar-fill.a { background: var(--color-a); }
        .bar-fill.b { background: var(--color-b); }
        .bar-fill.c { background: var(--color-c); }
        .bar-fill.d { background: var(--color-d); }

        /* Grid de alumnos */
        .student-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 6px;
        }
        .student-cell {
            aspect-ratio: 1;
            border-radius: 6px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            background: #2a2a3e;
            transition: all 0.3s;
        }
        .student-cell.answered { color: white; font-weight: bold; font-size: 0.9rem; }
        .student-cell.a { background: var(--color-a); }
        .student-cell.b { background: var(--color-b); }
        .student-cell.c { background: var(--color-c); }
        .student-cell.d { background: var(--color-d); }
        .student-cell .id { font-size: 0.65rem; opacity: 0.7; }

        /* Formulario de preguntas */
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 4px; color: var(--text-dim); font-size: 0.85rem; }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 8px 12px;
            background: #0a0a1a;
            border: 1px solid #0f3460;
            border-radius: 6px;
            color: var(--text);
            font-size: 0.95rem;
        }
        .form-group textarea { resize: vertical; min-height: 60px; }
        .option-input { display: flex; gap: 8px; align-items: center; }
        .option-input .letter {
            width: 30px; height: 30px; border-radius: 6px; display: flex;
            align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0;
        }
        .btn {
            padding: 8px 18px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            transition: transform 0.1s;
        }
        .btn:active { transform: scale(0.97); }
        .btn-primary { background: var(--color-b); color: white; }
        .btn-success { background: var(--color-c); color: white; }
        .btn-danger { background: var(--color-a); color: white; }
        .btn-warning { background: var(--color-d); color: white; }
        .btn-group { display: flex; gap: 8px; margin-top: 1rem; }

        /* Lista de preguntas */
        .question-list { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; }
        .question-item {
            padding: 10px;
            background: #0a0a1a;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        .question-item:hover { background: #0f3460; }
        .question-item.active { border-left: 3px solid var(--color-b); }
        .question-item .q-text { font-size: 0.85rem; flex: 1; }
        .question-item .q-correct { font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; }

        .empty-state { text-align: center; padding: 2rem; color: var(--text-dim); }
    </style>
</head>
<body>
    <div class="header">
        <h1>Py<span>Lickers</span></h1>
        <div class="status">
            <div class="status-dot" id="statusDot"></div>
            <span id="statusText">Desconectado</span>
        </div>
    </div>

    <div class="container">
        <div class="main-panel">
            <!-- Pregunta actual -->
            <div class="card">
                <h2>Pregunta Actual</h2>
                <div class="question-display" id="questionDisplay">
                    <div class="number" id="questionNumber"></div>
                    <div id="questionText">Selecciona una pregunta para empezar</div>
                    <div class="options" id="questionOptions" style="display:none;">
                        <div class="option a"><span class="count" id="countA">0</span>A: <span id="optA"></span></div>
                        <div class="option b"><span class="count" id="countB">0</span>B: <span id="optB"></span></div>
                        <div class="option c"><span class="count" id="countC">0</span>C: <span id="optC"></span></div>
                        <div class="option d"><span class="count" id="countD">0</span>D: <span id="optD"></span></div>
                    </div>
                </div>

                <!-- Resultados -->
                <div class="results-bars" id="resultsBars" style="display:none;">
                    <div class="bar-row">
                        <span class="bar-label" style="color:var(--color-a)">A</span>
                        <div class="bar-track"><div class="bar-fill a" id="barA" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <span class="bar-label" style="color:var(--color-b)">B</span>
                        <div class="bar-track"><div class="bar-fill b" id="barB" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <span class="bar-label" style="color:var(--color-c)">C</span>
                        <div class="bar-track"><div class="bar-fill c" id="barC" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <span class="bar-label" style="color:var(--color-d)">D</span>
                        <div class="bar-track"><div class="bar-fill d" id="barD" style="width:0%"></div></div>
                    </div>
                </div>

                <div class="btn-group">
                    <button class="btn btn-success" onclick="iniciarEscaneo()">Iniciar Escaneo</button>
                    <button class="btn btn-danger" onclick="pararEscaneo()">Parar</button>
                    <button class="btn btn-warning" onclick="resetRespuestas()">Reset</button>
                </div>
            </div>

            <!-- Crear pregunta -->
            <div class="card">
                <h2>Crear Pregunta</h2>
                <div class="form-group">
                    <label>Enunciado:</label>
                    <textarea id="newQuestion" placeholder="Escribe la pregunta..."></textarea>
                </div>
                <div class="form-group">
                    <label>Opciones:</label>
                    <div style="display:flex;flex-direction:column;gap:6px;">
                        <div class="option-input">
                            <div class="letter" style="background:var(--color-a)">A</div>
                            <input id="newOptA" placeholder="Opción A">
                        </div>
                        <div class="option-input">
                            <div class="letter" style="background:var(--color-b)">B</div>
                            <input id="newOptB" placeholder="Opción B">
                        </div>
                        <div class="option-input">
                            <div class="letter" style="background:var(--color-c)">C</div>
                            <input id="newOptC" placeholder="Opción C">
                        </div>
                        <div class="option-input">
                            <div class="letter" style="background:var(--color-d)">D</div>
                            <input id="newOptD" placeholder="Opción D">
                        </div>
                    </div>
                </div>
                <div class="form-group">
                    <label>Respuesta correcta:</label>
                    <div style="display:flex;gap:8px;">
                        <label><input type="radio" name="correct" value="A"> A</label>
                        <label><input type="radio" name="correct" value="B"> B</label>
                        <label><input type="radio" name="correct" value="C"> C</label>
                        <label><input type="radio" name="correct" value="D"> D</label>
                    </div>
                </div>
                <button class="btn btn-primary" onclick="guardarPregunta()">Guardar Pregunta</button>
            </div>
        </div>

        <!-- Panel lateral -->
        <div>
            <!-- Grid de alumnos -->
            <div class="card">
                <h2>Alumnos (<span id="detectedCount">0</span>/{{ num_alumnos }})</h2>
                <div class="student-grid" id="studentGrid">
                    {% for i in range(num_alumnos) %}
                    <div class="student-cell" id="student-{{ i }}">
                        <div class="id">#{{ i }}</div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <!-- Lista de preguntas -->
            <div class="card" style="margin-top: 1.5rem;">
                <h2>Preguntas ({{ preguntas|length }})</h2>
                <div class="question-list" id="questionList">
                    {% if preguntas %}
                        {% for p in preguntas %}
                        <div class="question-item" onclick="seleccionarPregunta({{ loop.index0 }})">
                            <span class="q-text">{{ loop.index }}. {{ p.texto[:50] }}...</span>
                            <span class="q-correct" style="background:var(--color-{{ p.correcta|lower }})">{{ p.correcta }}</span>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="empty-state">No hay preguntas aún</div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    <script>
        let preguntaActual = null;
        let respuestas = {};
        let polling = null;

        function seleccionarPregunta(idx) {
            fetch(`/api/pregunta/${idx}`)
                .then(r => r.json())
                .then(p => {
                    preguntaActual = p;
                    document.getElementById('questionNumber').textContent = `Pregunta ${idx + 1}`;
                    document.getElementById('questionText').textContent = p.texto;
                    document.getElementById('questionOptions').style.display = 'grid';
                    document.getElementById('optA').textContent = p.opciones.A;
                    document.getElementById('optB').textContent = p.opciones.B;
                    document.getElementById('optC').textContent = p.opciones.C;
                    document.getElementById('optD').textContent = p.opciones.D;
                    document.getElementById('resultsBars').style.display = 'flex';
                    resetRespuestas();
                });
        }

        function guardarPregunta() {
            const correcta = document.querySelector('input[name="correct"]:checked');
            if (!correcta) { alert('Selecciona la respuesta correcta'); return; }

            const data = {
                texto: document.getElementById('newQuestion').value,
                opciones: {
                    A: document.getElementById('newOptA').value,
                    B: document.getElementById('newOptB').value,
                    C: document.getElementById('newOptC').value,
                    D: document.getElementById('newOptD').value,
                },
                correcta: correcta.value
            };

            fetch('/api/preguntas', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(() => location.reload());
        }

        function iniciarEscaneo() {
            fetch('/api/sesion/iniciar', { method: 'POST' });
            document.getElementById('statusDot').classList.add('active');
            document.getElementById('statusText').textContent = 'Escaneando...';

            // Polling cada 500ms para actualizar respuestas
            polling = setInterval(actualizarRespuestas, 500);
        }

        function pararEscaneo() {
            fetch('/api/sesion/parar', { method: 'POST' });
            document.getElementById('statusDot').classList.remove('active');
            document.getElementById('statusText').textContent = 'Detenido';
            if (polling) clearInterval(polling);
        }

        function resetRespuestas() {
            fetch('/api/sesion/reset', { method: 'POST' });
            respuestas = {};
            actualizarUI();
        }

        function actualizarRespuestas() {
            fetch('/api/sesion/estado')
                .then(r => r.json())
                .then(data => {
                    respuestas = data.respuestas;
                    actualizarUI();
                });
        }

        function actualizarUI() {
            const total = Object.keys(respuestas).length;
            const conteo = { A: 0, B: 0, C: 0, D: 0 };

            // Reset grid
            for (let i = 0; i < {{ num_alumnos }}; i++) {
                const cell = document.getElementById(`student-${i}`);
                cell.className = 'student-cell';
                cell.innerHTML = `<div class="id">#${i}</div>`;
            }

            // Actualizar celdas con respuestas
            for (const [id, resp] of Object.entries(respuestas)) {
                const cell = document.getElementById(`student-${id}`);
                if (cell) {
                    cell.className = `student-cell answered ${resp.toLowerCase()}`;
                    cell.innerHTML = `${resp}<div class="id">#${id}</div>`;
                    conteo[resp]++;
                }
            }

            document.getElementById('detectedCount').textContent = total;

            // Barras y contadores
            for (const letra of ['A', 'B', 'C', 'D']) {
                const pct = total > 0 ? (conteo[letra] / total * 100) : 0;
                const bar = document.getElementById(`bar${letra}`);
                bar.style.width = `${pct}%`;
                bar.textContent = pct > 5 ? `${conteo[letra]} (${pct.toFixed(0)}%)` : '';
                document.getElementById(`count${letra}`).textContent = conteo[letra];
            }
        }
    </script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    datos = cargar_datos()
    return render_template_string(
        HTML_TEMPLATE,
        preguntas=datos["preguntas"],
        num_alumnos=NUM_ALUMNOS,
    )


@app.route("/api/preguntas", methods=["GET"])
def api_preguntas():
    datos = cargar_datos()
    return jsonify(datos["preguntas"])


@app.route("/api/preguntas", methods=["POST"])
def api_crear_pregunta():
    datos = cargar_datos()
    nueva = request.json
    datos["preguntas"].append(nueva)
    guardar_datos(datos)
    return jsonify({"ok": True, "id": len(datos["preguntas"]) - 1})


@app.route("/api/pregunta/<int:idx>")
def api_pregunta(idx):
    datos = cargar_datos()
    if 0 <= idx < len(datos["preguntas"]):
        return jsonify(datos["preguntas"][idx])
    return jsonify({"error": "No encontrada"}), 404


# ── API de sesión (el detector envía datos aquí) ──

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
    return jsonify({"ok": True})


@app.route("/api/sesion/respuestas", methods=["POST"])
def api_recibir_respuestas():
    """
    El detector envía las respuestas detectadas aquí.
    Formato esperado: {"respuestas": {"0": "A", "3": "C", ...}}
    """
    if sesion_activa["activa"]:
        nuevas = request.json.get("respuestas", {})
        sesion_activa["respuestas"].update(nuevas)
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════
NUM_ALUMNOS = 30

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyLickers - Interfaz del Profesor")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--alumnos", type=int, default=30)
    args = parser.parse_args()
    NUM_ALUMNOS = args.alumnos

    print(f"PyLickers Web arrancando en http://localhost:{args.port}")
    print(f"Alumnos configurados: {NUM_ALUMNOS}")
    app.run(host="0.0.0.0", port=args.port, debug=True)
