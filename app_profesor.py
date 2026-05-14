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

from flask import Flask, render_template_string, jsonify, request, Response
import json
import os
import argparse

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
            --bg: #101426;
            --card-bg: #17213b;
            --text: #f5f7ff;
            --text-dim: #9aa0b7;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { min-height: 100%; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg);
            color: var(--text);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            background: linear-gradient(90deg, #11122e, #161b45);
        }
        .header h1 { font-size: 1.6rem; letter-spacing: 1px; }
        .header h1 span { color: var(--color-b); }
        .header small { color: var(--text-dim); }
        .container {
            display: grid;
            grid-template-columns: 1.4fr 1fr;
            gap: 1.25rem;
            padding: 1.25rem;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 1.2rem;
        }
        .card h2 {
            font-size: 1.05rem;
            margin-bottom: 1rem;
            color: var(--color-b);
        }
        .form-group { margin-bottom: 0.9rem; }
        .form-group label { display: block; margin-bottom: 0.35rem; color: var(--text-dim); font-size: 0.85rem; }
        .form-group input,
        .form-group textarea,
        .form-group select {
            width: 100%;
            padding: 0.85rem 1rem;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.08);
            background: #101633;
            color: var(--text);
            font-size: 0.95rem;
        }
        .form-group textarea { min-height: 80px; resize: vertical; }
        .btn {
            padding: 0.85rem 1.2rem;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 700;
            color: white;
            margin-right: 0.65rem;
            margin-bottom: 0.5rem;
        }
        .btn-primary { background: var(--color-b); }
        .btn-secondary { background: #2d3461; }
        .btn-danger { background: var(--color-a); }
        .btn-group { display: flex; flex-wrap: wrap; gap: 0.7rem; }
        .small-note { color: var(--text-dim); font-size: 0.82rem; margin-top: 0.35rem; }
        .game-list,
        .question-list { display: grid; gap: 0.65rem; max-height: 280px; overflow-y: auto; }
        .game-item,
        .question-item {
            padding: 0.9rem 1rem;
            border-radius: 12px;
            background: rgba(255,255,255,0.03);
            cursor: pointer;
            transition: transform 0.15s ease, background 0.15s ease;
        }
        .game-item:hover,
        .question-item:hover { transform: translateY(-1px); background: rgba(255,255,255,0.06); }
        .game-item.active,
        .question-item.active { border: 1px solid rgba(52,152,219,0.7); }
        .game-item .title,
        .question-item .title { font-size: 0.95rem; margin-bottom: 0.35rem; }
        .question-item .meta { color: var(--text-dim); font-size: 0.82rem; }
        .question-display {
            border-radius: 16px;
            padding: 1.2rem;
            background: linear-gradient(180deg, rgba(17,20,54,0.95), rgba(22,27,69,0.95));
            border: 1px solid rgba(255,255,255,0.08);
        }
        .question-display .number { color: var(--text-dim); font-size: 0.82rem; margin-bottom: 0.5rem; }
        .question-display .text { font-size: 1.05rem; line-height: 1.5; }
        .options { display: grid; gap: 0.7rem; margin-top: 1rem; }
        .option { padding: 0.9rem 1rem; border-radius: 12px; background: #101433; }
        .option span { display: inline-block; min-width: 1.8rem; font-weight: 700; }
        .student-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 0.65rem; margin-top: 1rem; }
        .student-cell {
            padding: 0.75rem 0.5rem;
            border-radius: 12px;
            text-align: center;
            background: #12172f;
            border: 1px solid rgba(255,255,255,0.06);
            cursor: pointer;
        }
        .student-cell.answered { color: white; border-color: transparent; }
        .student-cell.a { background: rgba(231,76,60,0.9); }
        .student-cell.b { background: rgba(52,152,219,0.9); }
        .student-cell.c { background: rgba(46,204,113,0.9); }
        .student-cell.d { background: rgba(243,156,18,0.9); }
        .student-cell .id { font-size: 0.78rem; opacity: 0.8; margin-bottom: 0.25rem; }
        .student-cell .name { font-size: 0.82rem; }
        .results-bars { display: grid; gap: 0.7rem; margin-top: 1rem; }
        .bar-row { display: grid; grid-template-columns: 24px 1fr; gap: 0.65rem; align-items: center; }
        .bar-track { height: 18px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }
        .bar-fill { height: 100%; border-radius: 999px; display: flex; align-items: center; justify-content: flex-end; padding-right: 0.5rem; color: #fff; font-size: 0.72rem; font-weight: 700; }
        .bar-fill.a { background: rgba(231,76,60,0.9); }
        .bar-fill.b { background: rgba(52,152,219,0.9); }
        .bar-fill.c { background: rgba(46,204,113,0.9); }
        .bar-fill.d { background: rgba(243,156,18,0.9); }
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); z-index: 1000; justify-content: center; align-items: center; padding: 1rem; }
        .modal.visible { display: flex; }
        .modal-content { width: 100%; max-width: 420px; background: var(--card-bg); border-radius: 18px; padding: 1.4rem; border: 1px solid rgba(255,255,255,0.08); }
        .modal-close { float: right; cursor: pointer; font-size: 1.4rem; color: var(--text-dim); }

        @media (max-width: 1000px) {
            .container { grid-template-columns: 1fr; }
            .student-grid { grid-template-columns: repeat(4, minmax(0,1fr)); }
        }
        @media (max-width: 700px) {
            .student-grid { grid-template-columns: repeat(3, minmax(0,1fr)); }
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Py<span>Lickers</span></h1>
            <small>Panel del profesor</small>
        </div>
        <div class="small-note">Alumnos máximo 49 | Juegos como almacén de preguntas</div>
    </div>

    <div class="container">
        <div class="main-panel">
            <div class="card">
                <h2>Juegos</h2>
                <div class="game-list" id="gameList"></div>
                <div class="form-group">
                    <label>Nombre del juego</label>
                    <input id="newGameName" placeholder="Ej. Quiz de Historia">
                </div>
                <div class="form-group">
                    <label>Descripción</label>
                    <input id="newGameDescription" placeholder="Breve descripción">
                </div>
                <button class="btn btn-primary" onclick="guardarJuego()">Crear juego</button>
            </div>

            <div class="card">
                <h2>Pregunta Actual</h2>
                <div class="question-display" id="questionDisplay">
                    <div class="number" id="questionNumber">Selecciona un juego</div>
                    <div class="text" id="questionText">Eliga un juego para ver sus preguntas.</div>
                    <div class="options" id="questionOptions" style="display:none;"></div>
                </div>
                <div class="results-bars" id="resultsBars" style="display:none;">
                    <div class="bar-row">
                        <div class="bar-label">A</div>
                        <div class="bar-track"><div class="bar-fill a" id="barA" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <div class="bar-label">B</div>
                        <div class="bar-track"><div class="bar-fill b" id="barB" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <div class="bar-label">C</div>
                        <div class="bar-track"><div class="bar-fill c" id="barC" style="width:0%"></div></div>
                    </div>
                    <div class="bar-row">
                        <div class="bar-label">D</div>
                        <div class="bar-track"><div class="bar-fill d" id="barD" style="width:0%"></div></div>
                    </div>
                </div>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="iniciarEscaneo()">Iniciar Escaneo</button>
                    <button class="btn btn-secondary" onclick="pararEscaneo()">Parar</button>
                    <button class="btn btn-danger" onclick="resetRespuestas()">Reset</button>
                </div>
                <div class="question-list" id="questionList" style="margin-top:1rem;"></div>
            </div>

            <div class="card">
                <h2>Agregar pregunta</h2>
                <div class="form-group">
                    <label>Texto de la pregunta</label>
                    <textarea id="newQuestion" placeholder="Escribe la pregunta..."></textarea>
                </div>
                <div class="form-group">
                    <label>Opción A</label>
                    <input id="newOptA" placeholder="Opción A">
                </div>
                <div class="form-group">
                    <label>Opción B</label>
                    <input id="newOptB" placeholder="Opción B">
                </div>
                <div class="form-group">
                    <label>Opción C</label>
                    <input id="newOptC" placeholder="Opción C">
                </div>
                <div class="form-group">
                    <label>Opción D</label>
                    <input id="newOptD" placeholder="Opción D">
                </div>
                <div class="form-group">
                    <label>Respuesta correcta</label>
                    <select id="correctAnswer">
                        <option value="A">A</option>
                        <option value="B">B</option>
                        <option value="C">C</option>
                        <option value="D">D</option>
                    </select>
                </div>
                <button class="btn btn-primary" onclick="guardarPregunta()">Guardar pregunta</button>
                <div class="small-note">La pregunta se guarda en el juego seleccionado.</div>
            </div>
        </div>

        <div>
            <div class="card">
                <h2>Alumnos</h2>
                <div class="small-note">Detectados: <span id="detectedCount">0</span>/<span id="totalAlumnos">{{ num_alumnos }}</span></div>
                <div class="form-group">
                    <label>Número de alumnos</label>
                    <input type="number" id="numAlumnos" value="{{ num_alumnos }}" min="1" max="49" onchange="cambiarNumAlumnos()">
                </div>
                <div class="btn-group">
                    <button class="btn btn-secondary" onclick="asignarNumeros()">Asignar números</button>
                    <button class="btn btn-danger" onclick="resetearNombres()">Reset nombres</button>
                    <button class="btn btn-secondary" onclick="document.getElementById('importFile').click()">Importar TXT</button>
                    <a id="exportLink" class="btn btn-secondary" href="/api/alumnos/exportar?max={{ num_alumnos }}">Exportar TXT</a>
                </div>
                <input type="file" id="importFile" accept=".txt" style="display:none;">
                <div class="small-note">Importa un nombre por línea. La exportación descarga los nombres activos.</div>
                <div class="student-grid" id="studentGrid"></div>
                <div class="small-note" style="margin-top:0.75rem;">Click en una celda para asignar o editar nombre.</div>
            </div>
        </div>
    </div>

    <div id="modalEditor" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="cerrarEditorNombre()">×</span>
            <h2>Editar nombre</h2>
            <div class="form-group">
                <label>Alumno #<span id="editorNum"></span></label>
                <input type="text" id="inputNombre" placeholder="Nombre del alumno">
            </div>
            <div class="btn-group">
                <button class="btn btn-primary" onclick="guardarNombre()">Guardar</button>
                <button class="btn btn-secondary" onclick="cerrarEditorNombre()">Cancelar</button>
            </div>
        </div>
    </div>

    <script>
        let juegos = [];
        let preguntas = [];
        let currentGame = 0;
        let preguntaActualIdx = 0;
        let respuestas = {};
        let polling = null;
        let alumnosNombres = {};
        let editorAlumnoId = null;
        let numAlumnos = {{ num_alumnos }};

        function cargarJuegos() {
            fetch('/api/juegos')
                .then(r => r.json())
                .then(data => {
                    juegos = data;
                    renderGameList();
                    if (juegos.length > 0 && currentGame >= juegos.length) {
                        currentGame = 0;
                    }
                    renderGameList();
                    cargarPreguntas();
                });
        }

        function renderGameList() {
            const list = document.getElementById('gameList');
            list.innerHTML = '';
            juegos.forEach((juego, index) => {
                const item = document.createElement('div');
                item.className = 'game-item' + (index === currentGame ? ' active' : '');
                item.innerHTML = `<div class="title">${juego.nombre || 'Sin nombre'}</div><div class="meta">${juego.descripcion || 'Sin descripción'}</div>`;
                item.onclick = () => { currentGame = index; cargarPreguntas(); renderGameList(); };
                list.appendChild(item);
            });
        }

        function guardarJuego() {
            const nombre = document.getElementById('newGameName').value.trim();
            const descripcion = document.getElementById('newGameDescription').value.trim();
            if (!nombre) return alert('Ingresa un nombre de juego');
            fetch('/api/juegos', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ nombre, descripcion })
            }).then(() => {
                document.getElementById('newGameName').value = '';
                document.getElementById('newGameDescription').value = '';
                cargarJuegos();
            });
        }

        function cargarPreguntas() {
            if (!juegos.length) return;
            fetch(`/api/juegos/${currentGame}/preguntas`)
                .then(r => r.json())
                .then(data => {
                    preguntas = data;
                    preguntaActualIdx = 0;
                    renderQuestions();
                    mostrarPreguntaActual();
                });
        }

        function renderQuestions() {
            const list = document.getElementById('questionList');
            if (!list) return;
            list.innerHTML = '';
            preguntas.forEach((pregunta, index) => {
                const item = document.createElement('div');
                item.className = 'question-item' + (index === preguntaActualIdx ? ' active' : '');
                item.innerHTML = `<div class="title">${pregunta.texto}</div><div class="meta">${pregunta.opciones.A} · ${pregunta.opciones.B} · ${pregunta.opciones.C} · ${pregunta.opciones.D}</div>`;
                item.onclick = () => { preguntaActualIdx = index; mostrarPreguntaActual(); renderQuestions(); };
                list.appendChild(item);
            });
        }

        function mostrarPreguntaActual() {
            const details = document.getElementById('questionDisplay');
            const options = document.getElementById('questionOptions');
            if (!preguntas.length) {
                document.getElementById('questionNumber').textContent = 'Sin preguntas en este juego';
                document.getElementById('questionText').textContent = 'Crea preguntas y ubícalas dentro del juego seleccionado.';
                options.style.display = 'none';
                document.getElementById('resultsBars').style.display = 'none';
                return;
            }
            const pregunta = preguntas[preguntaActualIdx];
            document.getElementById('questionNumber').textContent = `Juego: ${juegos[currentGame]?.nombre || 'Sin juego'} · Pregunta ${preguntaActualIdx + 1}/${preguntas.length}`;
            document.getElementById('questionText').textContent = pregunta.texto;
            options.style.display = 'grid';
            options.innerHTML = `
                <div class="option a"><span>A</span>${pregunta.opciones.A}</div>
                <div class="option b"><span>B</span>${pregunta.opciones.B}</div>
                <div class="option c"><span>C</span>${pregunta.opciones.C}</div>
                <div class="option d"><span>D</span>${pregunta.opciones.D}</div>
            `;
            document.getElementById('resultsBars').style.display = 'grid';
        }

        function guardarPregunta() {
            if (!juegos.length) return alert('Crea y selecciona un juego antes.');
            const pregunta = {
                texto: document.getElementById('newQuestion').value.trim(),
                opciones: {
                    A: document.getElementById('newOptA').value.trim(),
                    B: document.getElementById('newOptB').value.trim(),
                    C: document.getElementById('newOptC').value.trim(),
                    D: document.getElementById('newOptD').value.trim(),
                },
                correcta: document.getElementById('correctAnswer').value
            };
            if (!pregunta.texto) return alert('Completa la pregunta');
            fetch(`/api/juegos/${currentGame}/preguntas`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(pregunta)
            }).then(() => {
                ['newQuestion', 'newOptA', 'newOptB', 'newOptC', 'newOptD'].forEach(id => document.getElementById(id).value = '');
                cargarPreguntas();
            });
        }

        function cargarNombresAlumnos() {
            fetch('/api/alumnos')
                .then(r => r.json())
                .then(data => {
                    alumnosNombres = data;
                    renderStudentGrid();
                    document.getElementById('exportLink').href = `/api/alumnos/exportar?max=${numAlumnos}`;
                });
        }

        function renderStudentGrid() {
            const grid = document.getElementById('studentGrid');
            grid.innerHTML = '';
            for (let i = 0; i < numAlumnos; i++) {
                const cell = document.createElement('div');
                const nombre = alumnosNombres[i]?.nombre || '';
                cell.className = 'student-cell';
                cell.id = `student-${i}`;
                cell.innerHTML = `<div class="id">#${i + 1}</div><div class="name">${nombre}</div>`;
                cell.onclick = () => abrirEditorNombre(i);
                grid.appendChild(cell);
            }
            actualizarUI();
        }

        function abrirEditorNombre(id) {
            editorAlumnoId = id;
            document.getElementById('editorNum').textContent = id + 1;
            document.getElementById('inputNombre').value = alumnosNombres[id]?.nombre || '';
            document.getElementById('modalEditor').classList.add('visible');
        }

        function cerrarEditorNombre() {
            document.getElementById('modalEditor').classList.remove('visible');
            editorAlumnoId = null;
        }

        function guardarNombre() {
            const nombre = document.getElementById('inputNombre').value.trim();
            fetch('/api/alumnos/asignar-nombre', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ id: editorAlumnoId, nombre })
            }).then(() => {
                alumnosNombres[editorAlumnoId] = { nombre };
                renderStudentGrid();
                cerrarEditorNombre();
            });
        }

        function asignarNumeros() {
            for (let i = 0; i < numAlumnos; i++) {
                const nombre = `Alumno ${i + 1}`;
                fetch('/api/alumnos/asignar-nombre', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ id: i, nombre })
                });
            }
            setTimeout(cargarNombresAlumnos, 500);
        }

        function resetearNombres() {
            if (!confirm('¿Borrar todos los nombres?')) return;
            fetch('/api/alumnos/reset', { method: 'POST' })
                .then(() => {
                    alumnosNombres = {};
                    renderStudentGrid();
                });
        }

        function actualizarUI() {
            const total = Object.keys(respuestas).length;
            const conteo = { A: 0, B: 0, C: 0, D: 0 };
            for (let i = 0; i < numAlumnos; i++) {
                const cell = document.getElementById(`student-${i}`);
                if (!cell) continue;
                const nombre = alumnosNombres[i]?.nombre || '';
                cell.className = 'student-cell';
                cell.innerHTML = `<div class="id">#${i + 1}</div><div class="name">${nombre}</div>`;
            }
            for (const [id, resp] of Object.entries(respuestas)) {
                const idx = Number(id);
                const cell = document.getElementById(`student-${idx}`);
                if (cell) {
                    cell.className = `student-cell answered ${resp.toLowerCase()}`;
                    const nombre = alumnosNombres[idx]?.nombre || '';
                    cell.innerHTML = `<div class="id">#${idx + 1}</div><div class="name">${nombre}</div>`;
                    conteo[resp] = (conteo[resp] || 0) + 1;
                }
            }
            document.getElementById('detectedCount').textContent = `${total}/${numAlumnos}`;
            ['A','B','C','D'].forEach(letra => {
                const bar = document.getElementById(`bar${letra}`);
                const pct = total > 0 ? Math.round(conteo[letra] / total * 100) : 0;
                bar.style.width = `${pct}%`;
                bar.textContent = pct > 8 ? `${conteo[letra]} (${pct}%)` : '';
                document.getElementById(`count${letra}`)?.textContent = conteo[letra] || 0;
            });
        }

        function cambiarNumAlumnos() {
            let nuevoNum = parseInt(document.getElementById('numAlumnos').value, 10);
            if (Number.isNaN(nuevoNum)) nuevoNum = {{ num_alumnos }};
            nuevoNum = Math.min(Math.max(nuevoNum, 1), 49);
            numAlumnos = nuevoNum;
            document.getElementById('numAlumnos').value = numAlumnos;
            document.getElementById('exportLink').href = `/api/alumnos/exportar?max=${numAlumnos}`;
            document.getElementById('totalAlumnos').textContent = numAlumnos;
            renderStudentGrid();
        }

        function iniciarEscaneo() {
            fetch('/api/sesion/iniciar', { method: 'POST' });
            polling = setInterval(actualizarRespuestas, 500);
        }

        function pararEscaneo() {
            fetch('/api/sesion/parar', { method: 'POST' });
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
                    respuestas = data.respuestas || {};
                    actualizarUI();
                });
        }

        document.getElementById('importFile').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            fetch(`/api/alumnos/importar?max=${numAlumnos}`, { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    if (data.error) return alert(data.error);
                    alert(`Importados ${data.imported} alumnos`);
                    cargarNombresAlumnos();
                });
        });

        cargarJuegos();
        cargarNombresAlumnos();
    </script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, num_alumnos=NUM_ALUMNOS)


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
