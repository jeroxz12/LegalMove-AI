"""Genera el par 3b (SaaS, solo cambia el precio) renderizando texto con una misma plantilla.

Sin IA generativa: original y enmienda salen del mismo texto y difieren solo en la Cláusula 3.
Requiere las fuentes Times New Roman de macOS. Revisá ambas imágenes antes de usarlas.

Uso (desde la raíz del repo): .venv/bin/python scripts/render_test_pair.py
"""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path("data/test_contracts")
FONTS_DIR = Path("/System/Library/Fonts/Supplemental")
WIDTH, HEIGHT = 1242, 1755
MARGIN = 150
WRAP_CHARS = 95

TITLE = "CONTRATO DE SERVICIO SAAS"
PREAMBLE = ('Este acuerdo se celebra el 1 de febrero de 2024 entre CloudMetrics Ltd. ("Proveedor") '
            'y RetailPulse S.A. ("Cliente").')
CLAUSES = [
    ("1. Servicio", "El Proveedor brindará acceso a la plataforma de análisis CloudMetrics."),
    ("2. Plazo de Suscripción", "La suscripción tendrá una duración de 12 meses."),
    ("3. Precio", "El Cliente pagará una tarifa mensual de USD {price}."),
    ("4. Disponibilidad del Servicio", "El Proveedor garantiza una disponibilidad del servicio del 99,5%."),
    ("5. Soporte", "El soporte al cliente se brindará vía correo electrónico."),
]
VERSIONS = {"documento_3b__original.jpg": "1.200", "documento_3b__enmienda.jpg": "1.250"}


def render(price: str, path: Path) -> None:
    regular = ImageFont.truetype(str(FONTS_DIR / "Times New Roman.ttf"), 26)
    bold = ImageFont.truetype(str(FONTS_DIR / "Times New Roman Bold.ttf"), 26)
    title_font = ImageFont.truetype(str(FONTS_DIR / "Times New Roman Bold.ttf"), 34)

    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    y = 150
    title_width = draw.textlength(TITLE, font=title_font)
    draw.text(((WIDTH - title_width) / 2, y), TITLE, font=title_font, fill="black")
    y += 80

    for line in textwrap.wrap(PREAMBLE, WRAP_CHARS):
        draw.text((MARGIN, y), line, font=regular, fill="black")
        y += 34
    y += 30

    for heading, body in CLAUSES:
        draw.text((MARGIN, y), heading, font=bold, fill="black")
        y += 34
        for line in textwrap.wrap(body.format(price=price), WRAP_CHARS):
            draw.text((MARGIN, y), line, font=regular, fill="black")
            y += 34
        y += 30

    image.save(path, quality=92)


if __name__ == "__main__":
    for file_name, price in VERSIONS.items():
        render(price, OUTPUT_DIR / file_name)
        print(f"Generado {OUTPUT_DIR / file_name}")
