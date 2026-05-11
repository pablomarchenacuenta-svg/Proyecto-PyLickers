#!/usr/bin/env python3
"""
GENERADOR DE TARJETAS PyLickers
================================
Genera tarjetas imprimibles con marcadores ArUco para usar en clase.
Cada tarjeta tiene un ID único de alumno, las letras A/B/C/D en los bordes,
y un marcador ArUco central que permite detectar la orientación.

Uso:
    python generar_tarjetas.py                  # Genera 30 tarjetas (por defecto)
    python generar_tarjetas.py --alumnos 25     # Genera 25 tarjetas
    python generar_tarjetas.py --nombres lista.txt  # Usa nombres de archivo

El archivo lista.txt debe tener un nombre por línea.
"""

import argparse
import cv2
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
import io
import os
import tempfile


# ── Configuración ──────────────────────────────────────────────
ARUCO_DICT = cv2.aruco.DICT_4X4_50  # Diccionario con 50 marcadores 4x4
CARD_WIDTH = 85 * mm    # Ancho tarjeta (como tarjeta de crédito)
CARD_HEIGHT = 85 * mm   # Alto tarjeta (cuadrada para rotación)
MARKER_SIZE = 45 * mm   # Tamaño del marcador ArUco
MARGIN = 15 * mm         # Margen de página
CARDS_PER_ROW = 2
CARDS_PER_COL = 3
CARDS_PER_PAGE = CARDS_PER_ROW * CARDS_PER_COL

# Colores
COLOR_A = HexColor("#E74C3C")  # Rojo
COLOR_B = HexColor("#3498DB")  # Azul
COLOR_C = HexColor("#2ECC71")  # Verde
COLOR_D = HexColor("#F39C12")  # Naranja
COLOR_BORDER = HexColor("#2C3E50")
COLOR_BG = HexColor("#FAFAFA")
COLOR_ID = HexColor("#7F8C8D")


def generar_marcador_aruco(marker_id, size_px=200):
    """Genera una imagen de marcador ArUco como array numpy."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_px)
    return marker_img


def guardar_marcador_temporal(marker_id, size_px=200):
    """Guarda un marcador ArUco como imagen temporal y devuelve la ruta."""
    marker_img = generar_marcador_aruco(marker_id, size_px)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    cv2.imwrite(tmp.name, marker_img)
    return tmp.name


def dibujar_tarjeta(c, x, y, student_id, student_name=None):
    """
    Dibuja una tarjeta individual en la posición (x, y).
    La tarjeta tiene:
    - Marco con bordes redondeados
    - Marcador ArUco central
    - Letras A/B/C/D en los cuatro lados
    - ID del alumno y nombre (opcional)
    """
    # ── Fondo de tarjeta ──
    c.setFillColor(COLOR_BG)
    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(1.5)
    c.roundRect(x, y, CARD_WIDTH, CARD_HEIGHT, 5 * mm, fill=1, stroke=1)

    # ── Centro de la tarjeta ──
    cx = x + CARD_WIDTH / 2
    cy = y + CARD_HEIGHT / 2

    # ── Marcador ArUco ──
    marker_path = guardar_marcador_temporal(student_id, size_px=300)
    img_x = cx - MARKER_SIZE / 2
    img_y = cy - MARKER_SIZE / 2
    c.drawImage(marker_path, img_x, img_y, MARKER_SIZE, MARKER_SIZE)
    os.unlink(marker_path)

    # ── Letras A, B, C, D ──
    # Las letras están posicionadas para que al girar la tarjeta,
    # la letra que queda arriba indica la respuesta.
    letter_offset = 6 * mm  # Distancia desde el borde
    font_size = 22

    # A = arriba (posición normal)
    c.setFillColor(COLOR_A)
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(cx, y + CARD_HEIGHT - letter_offset - 4 * mm, "A")

    # B = derecha (tarjeta girada 90° horario)
    c.setFillColor(COLOR_B)
    c.drawCentredString(x + CARD_WIDTH - letter_offset, cy - 3 * mm, "B")

    # C = abajo (tarjeta girada 180°)
    c.setFillColor(COLOR_C)
    c.drawCentredString(cx, y + letter_offset, "C")

    # D = izquierda (tarjeta girada 270°)
    c.setFillColor(COLOR_D)
    c.drawCentredString(x + letter_offset, cy - 3 * mm, "D")

    # ── Pequeños indicadores de color en esquinas ──
    dot_r = 3 * mm
    dot_margin = 8 * mm
    # Esquina superior-izq (entre A y D)
    c.setFillColor(COLOR_A)
    c.circle(x + dot_margin, y + CARD_HEIGHT - dot_margin, dot_r, fill=1, stroke=0)
    # Esquina superior-der (entre A y B)
    c.setFillColor(COLOR_B)
    c.circle(x + CARD_WIDTH - dot_margin, y + CARD_HEIGHT - dot_margin, dot_r, fill=1, stroke=0)
    # Esquina inferior-der (entre B y C)
    c.setFillColor(COLOR_C)
    c.circle(x + CARD_WIDTH - dot_margin, y + dot_margin, dot_r, fill=1, stroke=0)
    # Esquina inferior-izq (entre C y D)
    c.setFillColor(COLOR_D)
    c.circle(x + dot_margin, y + dot_margin, dot_r, fill=1, stroke=0)

    # ── ID del alumno ──
    c.setFillColor(COLOR_ID)
    c.setFont("Helvetica", 8)
    id_text = f"#{student_id:02d}"
    if student_name:
        id_text += f" - {student_name}"
    c.drawCentredString(cx, y + CARD_HEIGHT - 3.5 * mm, id_text)


def generar_pdf(output_path, num_alumnos=30, nombres=None):
    """Genera el PDF completo con todas las tarjetas."""
    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    # Calcular posiciones centradas en la página
    total_w = CARDS_PER_ROW * CARD_WIDTH + (CARDS_PER_ROW - 1) * 8 * mm
    total_h = CARDS_PER_COL * CARD_HEIGHT + (CARDS_PER_COL - 1) * 8 * mm
    start_x = (page_w - total_w) / 2
    start_y = page_h - (page_h - total_h) / 2

    for i in range(num_alumnos):
        pos_in_page = i % CARDS_PER_PAGE

        if pos_in_page == 0 and i > 0:
            c.showPage()

        row = pos_in_page // CARDS_PER_ROW
        col = pos_in_page % CARDS_PER_ROW

        x = start_x + col * (CARD_WIDTH + 8 * mm)
        y = start_y - (row + 1) * (CARD_HEIGHT + 8 * mm)

        nombre = nombres[i] if nombres and i < len(nombres) else None
        dibujar_tarjeta(c, x, y, student_id=i, student_name=nombre)

    # ── Página de instrucciones al final ──
    c.showPage()
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(COLOR_BORDER)
    c.drawCentredString(page_w / 2, page_h - 3 * cm, "PyLickers - Instrucciones")

    c.setFont("Helvetica", 12)
    instrucciones = [
        "1. Recorta cada tarjeta por el borde.",
        "2. Cada alumno recibe una tarjeta con su número.",
        "3. Para responder, sostén la tarjeta con la letra elegida ARRIBA:",
        "",
        "   A = letra roja arriba (posición normal)",
        "   B = letra azul arriba (girar 90° a la derecha)",
        "   C = letra verde arriba (girar 180°, boca abajo)",
        "   D = letra naranja arriba (girar 90° a la izquierda)",
        "",
        "4. El profesor escanea la clase con la webcam.",
        "5. El sistema detecta automáticamente cada tarjeta y su orientación.",
        "",
        f"Tarjetas generadas: {num_alumnos}",
        f"Diccionario ArUco: 4x4_50",
    ]
    y_pos = page_h - 5 * cm
    for line in instrucciones:
        c.drawString(3 * cm, y_pos, line)
        y_pos -= 18

    c.save()
    print(f"PDF generado: {output_path}")
    print(f"Tarjetas: {num_alumnos}")
    print(f"Páginas: {(num_alumnos + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE + 1}")


def main():
    parser = argparse.ArgumentParser(description="Generador de tarjetas PyLickers")
    parser.add_argument("--alumnos", type=int, default=30,
                        help="Número de tarjetas a generar (máx. 50)")
    parser.add_argument("--nombres", type=str, default=None,
                        help="Archivo .txt con nombres (uno por línea)")
    parser.add_argument("--output", type=str, default="tarjetas_pylickers.pdf",
                        help="Nombre del archivo PDF de salida")
    args = parser.parse_args()

    if args.alumnos > 50:
        print("Error: El diccionario ArUco 4x4_50 sólo tiene 50 marcadores.")
        print("Usa --alumnos 50 como máximo.")
        return

    nombres = None
    if args.nombres:
        with open(args.nombres, "r", encoding="utf-8") as f:
            nombres = [line.strip() for line in f if line.strip()]

    generar_pdf(args.output, args.alumnos, nombres)


if __name__ == "__main__":
    main()
