#!/usr/bin/env python3
"""
PyLickers - PROTOTIPO DETECTOR
================================
Detecta tarjetas ArUco mediante la webcam y determina la respuesta
de cada alumno según la orientación del marcador.

Uso:
    python detector.py                  # Ejecutar con webcam por defecto
    python detector.py --camara 1       # Usar cámara con índice 1
    python detector.py --debug          # Mostrar 
    info extra de depuración

Controles:
    Q / ESC  → Salir
    S        → Capturar respuestas actuales (snapshot)
    R        → Resetear respuestas
    D        → Activar/desactivar modo debug

Requisitos:
    pip install opencv-contrib-python numpy
"""

import cv2
import numpy as np
import threading
import io
import argparse
import json
import time
import requests
from datetime import datetime
from collections import defaultdict


# ══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════

ARUCO_DICT = cv2.aruco.DICT_4X4_50
NUM_ALUMNOS = 30  # Ajustar al número real de alumnos

# Colores BGR para cada respuesta
COLORES = {
    "A": (60, 76, 231),    # Rojo
    "B": (219, 152, 52),   # Azul
    "C": (113, 204, 46),   # Verde
    "D": (18, 156, 243),   # Naranja
}
COLOR_FONDO = (45, 45, 45)
COLOR_TEXTO = (255, 255, 255)
COLOR_DETECTADO = (0, 255, 0)
COLOR_NO_DETECTADO = (100, 100, 100)


# ══════════════════════════════════════════════════════════════════
# FUNCIONES DE DETECCIÓN
# ══════════════════════════════════════════════════════════════════

def inicializar_detector():
    """Configura el diccionario ArUco y los parámetros del detector."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    parametros = cv2.aruco.DetectorParameters()

    # Ajustes para mejorar la detección en condiciones de aula
    parametros.adaptiveThreshWinSizeMin = 3
    parametros.adaptiveThreshWinSizeMax = 23
    parametros.adaptiveThreshWinSizeStep = 10
    parametros.adaptiveThreshConstant = 7
    parametros.minMarkerPerimeterRate = 0.03
    parametros.maxMarkerPerimeterRate = 4.0
    parametros.polygonalApproxAccuracyRate = 0.03
    parametros.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

    detector = cv2.aruco.ArucoDetector(aruco_dict, parametros)
    return detector


def determinar_respuesta(corners, num_alumnos=NUM_ALUMNOS):
    """
    Determina la respuesta (A/B/C/D) a partir de la orientación del marcador.

    La primera esquina del marcador ArUco es siempre la esquina superior-izquierda
    del marcador en su orientación original. Al detectar la rotación de esta
    esquina respecto al centro, sabemos cómo está girada la tarjeta.

    Orientaciones:
        Primera esquina arriba-izq → A (0° rotación)
        Primera esquina arriba-der → B (90° rotación horaria)
        Primera esquina abajo-der  → C (180° rotación)
        Primera esquina abajo-izq  → D (270° rotación horaria)
    """
    # Esquinas del marcador detectado
    pts = corners[0]  # Shape: (4, 2)

    # Centro del marcador
    centro = np.mean(pts, axis=0)

    # Primera esquina (la que ArUco identifica como esquina 0)
    primera = pts[0]

    # Calcular ángulo desde el centro a la primera esquina
    dx = primera[0] - centro[0]
    dy = primera[1] - centro[1]
    angulo = np.degrees(np.arctan2(dy, dx))

    # Normalizar a [0, 360)
    angulo = angulo % 360

    # Clasificar según cuadrante
    # Primera esquina arriba-izquierda (ángulo ~225°) → A
    # Primera esquina arriba-derecha (ángulo ~315°) → B
    # Primera esquina abajo-derecha (ángulo ~45°) → C
    # Primera esquina abajo-izquierda (ángulo ~135°) → D
    if 180 <= angulo < 270:
        return "A"
    elif 270 <= angulo < 360:
        return "B"
    elif 0 <= angulo < 90:
        return "C"
    else:  # 90 <= angulo < 180
        return "D"


def detectar_tarjetas(frame, detector, num_alumnos=NUM_ALUMNOS):
    """
    Detecta todos los marcadores ArUco en el frame.
    Devuelve un diccionario {id_alumno: respuesta}.
    """
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gris)

    respuestas = {}

    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            if 0 <= marker_id < num_alumnos:
                respuesta = determinar_respuesta(corners[i], num_alumnos=num_alumnos)
                respuestas[int(marker_id)] = respuesta

    return respuestas, corners, ids


# ══════════════════════════════════════════════════════════════════
# FUNCIONES DE VISUALIZACIÓN
# ══════════════════════════════════════════════════════════════════

def dibujar_detecciones(frame, corners, ids, respuestas, num_alumnos=NUM_ALUMNOS):
    """Dibuja los marcadores detectados sobre el frame de la cámara."""
    if ids is None:
        return frame

    for i, marker_id in enumerate(ids.flatten()):
        if marker_id >= num_alumnos:
            continue

        pts = corners[i][0].astype(int)
        respuesta = respuestas.get(int(marker_id), "?")
        color = COLORES.get(respuesta, (255, 255, 255))

        # Dibujar contorno del marcador
        cv2.polylines(frame, [pts], True, color, 3)

        # Etiqueta con ID y respuesta
        centro = np.mean(pts, axis=0).astype(int)
        texto = f"#{marker_id}: {respuesta}"

        # Fondo de la etiqueta
        (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(frame,
                      (centro[0] - tw // 2 - 5, centro[1] - th - 10),
                      (centro[0] + tw // 2 + 5, centro[1] + 5),
                      color, -1)
        cv2.putText(frame, texto,
                    (centro[0] - tw // 2, centro[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return frame


def dibujar_panel_estado(frame, respuestas_acumuladas, respuestas_actuales, num_alumnos=NUM_ALUMNOS):
    """
    Dibuja un panel lateral con el estado de todos los alumnos.
    Muestra quién ha sido detectado y su última respuesta.
    """
    h, w = frame.shape[:2]
    panel_w = 220
    panel = np.full((h, panel_w, 3), 45, dtype=np.uint8)

    # Título
    cv2.putText(panel, "PyLickers", (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(panel, f"Detectados: {len(respuestas_actuales)}/{NUM_ALUMNOS}",
                (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    # Línea separadora
    cv2.line(panel, (10, 65), (panel_w - 10, 65), (100, 100, 100), 1)

    # Grid de alumnos
    cols = 5
    cell_size = 35
    start_x = 15
    start_y = 80

    for alumno_id in range(num_alumnos):
        row = alumno_id // cols
        col = alumno_id % cols
        x = start_x + col * (cell_size + 5)
        y = start_y + row * (cell_size + 5)

        # Color según estado
        if alumno_id in respuestas_actuales:
            resp = respuestas_actuales[alumno_id]
            color = COLORES.get(resp, (150, 150, 150))
            cv2.rectangle(panel, (x, y), (x + cell_size, y + cell_size), color, -1)
            # Letra de respuesta
            cv2.putText(panel, resp, (x + 10, y + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        elif alumno_id in respuestas_acumuladas:
            resp = respuestas_acumuladas[alumno_id]
            color = COLORES.get(resp, (150, 150, 150))
            # Versión más oscura (ya detectado pero no visible ahora)
            dark_color = tuple(c // 2 for c in color)
            cv2.rectangle(panel, (x, y), (x + cell_size, y + cell_size), dark_color, -1)
            cv2.putText(panel, resp, (x + 10, y + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        else:
            cv2.rectangle(panel, (x, y), (x + cell_size, y + cell_size),
                          (80, 80, 80), -1)
            # Mostrar número de alumno en base 1
            cv2.putText(panel, f"{alumno_id + 1}", (x + 3, y + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1)

    # ── Barra de resumen ──
    total = len(respuestas_acumuladas)
    if total > 0:
        bar_y = start_y + ((NUM_ALUMNOS // cols) + 1) * (cell_size + 5) + 10
        cv2.putText(panel, "Resumen:", (15, bar_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        bar_y += 25

        conteo = defaultdict(int)
        for resp in respuestas_acumuladas.values():
            conteo[resp] += 1

        bar_width = panel_w - 30
        for letra in ["A", "B", "C", "D"]:
            n = conteo[letra]
            pct = n / total if total > 0 else 0
            color = COLORES[letra]

            # Barra
            bw = int(bar_width * pct)
            cv2.rectangle(panel, (15, bar_y), (15 + bw, bar_y + 18), color, -1)
            cv2.rectangle(panel, (15, bar_y), (15 + bar_width, bar_y + 18),
                          (100, 100, 100), 1)

            # Texto
            texto = f"{letra}: {n} ({pct * 100:.0f}%)"
            cv2.putText(panel, texto, (15 + bar_width + 5, bar_y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
            bar_y += 25

    # Controles
    ctrl_y = h - 80
    cv2.putText(panel, "Controles:", (15, ctrl_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    cv2.putText(panel, "S: Capturar  R: Reset", (15, ctrl_y + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 140), 1)
    cv2.putText(panel, "D: Debug  Q/ESC: Salir", (15, ctrl_y + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 140, 140), 1)

    # Combinar frame y panel
    resultado = np.hstack([frame, panel])
    return resultado


# ══════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="PyLickers - Detector de tarjetas")
    parser.add_argument("--camara", type=int, default=0,
                        help="Índice de la cámara (por defecto: 0)")
    parser.add_argument("--debug", action="store_true",
                        help="Activar modo debug")
    parser.add_argument("--alumnos", type=int, default=4,
                        help="Número de alumnos")
    args = parser.parse_args()

    global NUM_ALUMNOS
    NUM_ALUMNOS = args.alumnos

    # Inicializar
    print("Inicializando PyLickers...")
    detector = inicializar_detector()
    cap = cv2.VideoCapture(args.camara)

    if not cap.isOpened():
        print(f"Error: No se pudo abrir la cámara {args.camara}")
        print("Intenta con --camara 1 o comprueba que la webcam está conectada.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print(f"Cámara abierta. Resolución: {int(cap.get(3))}x{int(cap.get(4))}")
    print("Mostrando ventana... Pulsa Q o ESC para salir.")

    respuestas_acumuladas = {}  # Guarda la última respuesta de cada alumno
    modo_debug = args.debug
    last_send = 0
    # For coordinated resets with the web app
    server_reset_counter = 0
    try:
        r = requests.get("http://localhost:5000/api/sesion/estado", timeout=0.5)
        if r.ok:
            server_reset_counter = int(r.json().get("reset_counter", 0))
    except Exception:
        server_reset_counter = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: No se pudo leer el frame de la cámara.")
            break

        # Detectar tarjetas
        respuestas_actuales, corners, ids = detectar_tarjetas(frame, detector, num_alumnos=args.alumnos)

        # Acumular respuestas (la última detección gana)
        respuestas_acumuladas.update(respuestas_actuales)

        # Enviar respuestas a la web app cada segundo (cuando se usa como proceso independiente)
        current_time = time.time()
        if current_time - last_send > 1:
            try:
                requests.post("http://localhost:5000/api/sesion/respuestas", json={"respuestas": respuestas_acumuladas}, timeout=0.5)
                # Check server state for reset counter
                try:
                    r = requests.get("http://localhost:5000/api/sesion/estado", timeout=0.5)
                    if r.ok:
                        data = r.json()
                        srv = int(data.get("reset_counter", 0))
                        if srv > server_reset_counter:
                            # Server requested a reset -> clear local accumulated responses
                            respuestas_acumuladas = {}
                            server_reset_counter = srv
                            print("Detector: reset aplicado por servidor (reset_counter={})".format(server_reset_counter))
                except Exception:
                    pass
                last_send = current_time
            except:
                pass

        # Dibujar detecciones sobre el frame
        frame = dibujar_detecciones(frame, corners, ids, respuestas_actuales)

        # Debug: dibujar rechazados
        if modo_debug and ids is not None:
            cv2.putText(frame, f"DEBUG | Markers: {len(ids)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Panel lateral
        resultado = dibujar_panel_estado(frame, respuestas_acumuladas, respuestas_actuales)

        # Mostrar
        cv2.imshow("PyLickers", resultado)

        # Controles de teclado
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):  # Q o ESC
            break
        elif key == ord("s"):  # Snapshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pylickers_resultado_{timestamp}.json"
            datos = {
                "timestamp": timestamp,
                "respuestas": respuestas_acumuladas,
                "resumen": {
                    letra: sum(1 for v in respuestas_acumuladas.values() if v == letra)
                    for letra in "ABCD"
                },
                "total_detectados": len(respuestas_acumuladas),
            }
            with open(filename, "w") as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)
            print(f"Respuestas guardadas en {filename}")
        elif key == ord("r"):  # Schedule Reset (do not clear locally)
            try:
                requests.post("http://localhost:5000/api/sesion/schedule_reset", timeout=0.5)
                print("Detector: reset programado en servidor; se aplicará al avanzar la pregunta.")
            except Exception:
                print("Detector: no se pudo programar reset en servidor.")
        elif key == ord("d"):  # Debug toggle
            modo_debug = not modo_debug
            print(f"Debug: {'ON' if modo_debug else 'OFF'}")

    cap.release()
    cv2.destroyAllWindows()
    print("PyLickers cerrado.")


class DetectorThread(threading.Thread):
    """Hilo que ejecuta el detector en el mismo proceso.

    - Actualiza `sesion_activa['respuestas']` directamente.
    - Mantiene `latest_frame` como JPEG bytes para streaming.
    - Observa `sesion_activa['reset_counter']` para limpiar su estado.
    """

    def __init__(self, cam_index=0, sesion_activa=None, num_alumnos=NUM_ALUMNOS, show_window=False):
        super().__init__(daemon=True)
        self.cam_index = cam_index
        self.sesion_activa = sesion_activa or {}
        self.num_alumnos = num_alumnos
        self.show_window = show_window
        self.running = False
        self.latest_frame = None
        self._cap = None

    def get_latest_frame(self):
        return self.latest_frame

    def stop(self, timeout=2.0):
        self.running = False
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        if self.show_window:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    def run(self):
        detector = inicializar_detector()
        cap = cv2.VideoCapture(self.cam_index)
        self._cap = cap
        if not cap.isOpened():
            print(f"DetectorThread: no se pudo abrir la cámara {self.cam_index}")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        respuestas_acumuladas = {}
        last_reset_counter = int(self.sesion_activa.get('reset_counter', 0)) if self.sesion_activa else 0
        modo_debug = False
        self.running = True
        last_send = 0
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    break

                respuestas_actuales, corners, ids = detectar_tarjetas(frame, detector, num_alumnos=self.num_alumnos)
                respuestas_acumuladas.update(respuestas_actuales)

                # Apply server-requested reset_counter
                try:
                    srv = int(self.sesion_activa.get('reset_counter', 0)) if self.sesion_activa else 0
                    if srv > last_reset_counter:
                        respuestas_acumuladas = {}
                        last_reset_counter = srv
                except Exception:
                    pass

                # If server is pausing, buffer instead of updating
                if self.sesion_activa and self.sesion_activa.get('pausing'):
                    self.sesion_activa.setdefault('incoming_buffer', []).append(respuestas_actuales)
                else:
                    if self.sesion_activa is not None:
                        self.sesion_activa.setdefault('respuestas', {}).update(respuestas_acumuladas)

                # Draw overlays
                resultado = dibujar_detecciones(frame, corners, ids, respuestas_actuales, num_alumnos=self.num_alumnos)
                resultado = dibujar_panel_estado(resultado, respuestas_acumuladas, respuestas_actuales, num_alumnos=self.num_alumnos)

                # Encode to JPEG for streaming
                try:
                    ret2, jpg = cv2.imencode('.jpg', resultado, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if ret2:
                        self.latest_frame = jpg.tobytes()
                except Exception:
                    self.latest_frame = None

                # If show_window, display and handle keys
                if self.show_window:
                    cv2.imshow('PyLickers', resultado)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord('q'), 27):
                        break
                    elif key == ord('s'):
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"pylickers_resultado_{timestamp}.json"
                        datos = {
                            'timestamp': timestamp,
                            'respuestas': respuestas_acumuladas,
                            'resumen': { letra: sum(1 for v in respuestas_acumuladas.values() if v == letra) for letra in 'ABCD' },
                            'total_detectados': len(respuestas_acumuladas),
                        }
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(datos, f, indent=2, ensure_ascii=False)
                        print(f"Respuestas guardadas en {filename}")
                    elif key == ord('r'):
                        # schedule reset in server (if present)
                        try:
                            requests.post('http://localhost:5000/api/sesion/schedule_reset', timeout=0.5)
                            print('Detector: reset programado en servidor; se aplicará al avanzar la pregunta.')
                        except Exception:
                            print('Detector: no se pudo programar reset en servidor.')
                    elif key == ord('d'):
                        modo_debug = not modo_debug
                        print(f'Debug: {"ON" if modo_debug else "OFF"}')

                # Sleep a bit to avoid hogging CPU
                time.sleep(0.01)
        finally:
            try:
                cap.release()
            except Exception:
                pass
            if self.show_window:
                try:
                    cv2.destroyAllWindows()
                except Exception:
                    pass


if __name__ == '__main__':
    main()


if __name__ == "__main__":
    main()
