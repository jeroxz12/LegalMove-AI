# Contratos de prueba

Referencia única de los casos de prueba y sus resultados esperados. Los criterios de evaluación están en `docs/architecture.md` (sección 8).

## Archivos

| Par | Contrato original | Enmienda | Tipo de enmienda |
|---|---|---|---|
| 1 – Licencia de software | `documento_1__original.jpg` | `documento_1__enmienda.jpg` | Reescrita |
| 2 – Servicios de consultoría | `documento_2__original.jpg` | `documento_2__enmienda.jpg` | Reescrita |
| 3 – Servicio SaaS | `documento_3__original.jpg` | `documento_3__enmienda.jpg` | Reescrita ("Versión actualizada") |
| 3b – SaaS, solo precio | `documento_3b__original.jpg` | `documento_3b__enmienda.jpg` | Reescrita |
| Texto instructivo | `instructivo__original.md` | `instructivo__enmienda.md` | Instructiva (sin imágenes) |

Las imágenes son de 1242×1755 px y fueron generadas digitalmente (no son escaneos).

Los archivos Word son material de origen:

- `Contratos y Enmiendas de ejemplo.docx`: texto de los seis documentos.
- `Diferencias entre Contratos y Enmiendas de ejemplo.docx`: lista de cambios. **Está incompleta:** omite los dos cambios de la Cláusula 1 del par 1. La referencia válida es este README.

## Convenciones

- Identificadores con el formato `Cláusula N`, únicos en `sections_changed`. Modificaciones y eliminaciones usan el número del original; adiciones, el número de la enmienda.
- Etiquetas aplicadas **por cambio, no por cláusula** (criterio aprobado en `docs/architecture.md`, sección 3):
  - `ADICIÓN`: nueva cláusula u obligación independiente.
  - `ELIMINACIÓN`: supresión sin reemplazo.
  - `MODIFICACIÓN`: sustitución o ampliación de algo existente.
- Una cláusula puede tener varios hechos de distinto tipo; en `sections_changed` aparece una sola vez.
- **No son cambios contractuales:** el título y el preámbulo propios de la enmienda ("La presente enmienda modifica...") y una renumeración sin cambio de contenido. Las partes y la fecha del contrato no cambian en ningún par.
- Los hechos describen el cambio textual. No afirman efectos legales.
- La revisión de exactitud es manual contra este README. Si en la etapa 7 se crea un JSON de hechos para las comprobaciones automáticas, debe coincidir con estas tablas.

## Par 1 – Licencia de software (caso complejo)

`sections_changed` esperado: `Cláusula 1`, `Cláusula 2`, `Cláusula 3`, `Cláusula 4`, `Cláusula 5`, `Cláusula 7`.

| # | Etiqueta | Cláusula | Antes | Después |
|---|---|---|---|---|
| 1.1 | ELIMINACIÓN | 1 – Otorgamiento de Licencia | "licencia no exclusiva e intransferible" | "licencia no exclusiva" |
| 1.2 | MODIFICACIÓN | 1 – Otorgamiento de Licencia | "únicamente para fines internos de la empresa" | "para operaciones internas de negocio" |
| 1.3 | MODIFICACIÓN | 2 – Plazo | 12 meses | 24 meses |
| 1.4 | MODIFICACIÓN | 3 – Pago | tarifa anual de USD 12.000 | tarifa anual de USD 15.000 |
| 1.5 | MODIFICACIÓN | 4 – Soporte | vía correo electrónico | vía correo electrónico y chat |
| 1.6 | MODIFICACIÓN | 5 – Terminación | 30 días de anticipación | 60 días de anticipación |
| 1.7 | ADICIÓN | 7 – Protección de Datos | — | Cumplimiento de normativas de protección de datos respecto de la información del Licenciatario |

Sin cambios: Cláusula 6 (Confidencialidad); en la Cláusula 3, el plazo de pago (30 días desde la factura); en la Cláusula 4, el horario laboral.

El hecho 1.2 es una reformulación del texto. Este README no determina si amplía o restringe el uso permitido; el resultado tampoco debería afirmarlo sin sustento.

## Par 2 – Servicios de consultoría (caso complejo adicional)

`sections_changed` esperado: `Cláusula 1`, `Cláusula 2`, `Cláusula 3`, `Cláusula 4`, `Cláusula 7`.

| # | Etiqueta | Cláusula | Antes | Después |
|---|---|---|---|---|
| 2.1 | MODIFICACIÓN | 1 – Alcance del Servicio | "...expansión de proyectos de energía renovable." | "...expansión de proyectos de energía renovable y análisis regulatorio." |
| 2.2 | MODIFICACIÓN | 2 – Duración | 6 meses | 9 meses |
| 2.3 | MODIFICACIÓN | 3 – Honorarios | tarifa mensual de USD 8.000 | tarifa mensual de USD 9.500 |
| 2.4 | MODIFICACIÓN | 4 – Entregables | reportes mensuales de avance | reportes quincenales de avance |
| 2.5 | ADICIÓN | 7 – Propiedad Intelectual | — | Los entregables pasan a ser propiedad del Cliente una vez realizado el pago final |

Sin cambios: Cláusula 5 (Confidencialidad), Cláusula 6 (Legislación Aplicable, Estado de California); en la Cláusula 4, el informe final.

No se espera ninguna `[ELIMINACIÓN]`.

## Par 3 – Servicio SaaS

`sections_changed` esperado: `Cláusula 3`, `Cláusula 4`, `Cláusula 5`.

| # | Etiqueta | Cláusula | Antes | Después |
|---|---|---|---|---|
| 3.1 | MODIFICACIÓN | 3 – Precio | tarifa mensual de USD 1.200 | tarifa mensual de USD 1.250 |
| 3.2 | MODIFICACIÓN | 4 – Disponibilidad del Servicio | 99,5% | 99,9% |
| 3.3 | MODIFICACIÓN | 5 – Soporte | vía correo electrónico | vía correo electrónico y sistema de tickets en línea |

Sin cambios: Cláusula 1 (Servicio), Cláusula 2 (Plazo de Suscripción, 12 meses). El preámbulo es idéntico; el título agrega "– VERSIÓN ACTUALIZADA".

No se espera ninguna `[ADICIÓN]` ni `[ELIMINACIÓN]`.

## Casos planificados (todavía no creados)

Las imágenes nuevas se generan en la etapa 7 de forma determinista: renderizado de texto a imagen con una misma plantilla para original y enmienda, sin IA generativa. Ambas imágenes de cada par se revisan visualmente antes de aceptarlas. Los nombres de archivo se definen al crearlas.

### Par 3b – SaaS, solo precio (caso simple de la defensa) — creado

Generado con `.venv/bin/python scripts/render_test_pair.py` y revisado visualmente el 02/11/2026.

- Original y enmienda generados con la misma plantilla, con el texto del contrato SaaS original.
- La enmienda difiere **solo** en el precio de la Cláusula 3.
- `sections_changed` esperado: `Cláusula 3`.
- Único hecho: `[MODIFICACIÓN]` Cláusula 3 – Precio, tarifa mensual de USD 1.200 a USD 1.250.
- Sin cambios: Cláusulas 1, 2, 4 y 5.

### Texto instructivo (sin imágenes) y par 4

Comprueba que, en una enmienda instructiva, la ausencia de una cláusula no se reporte como eliminación, y que una eliminación expresa de una cláusula completa sí se reporte.

- **Texto instructivo (etapas 3 y 4, creado):** `instructivo__original.md` y `instructivo__enmienda.md`. Se usa directamente como entrada de los agentes, sin pasar por Vision.
- **Par 4 (etapa 7):** el mismo contenido renderizado en dos imágenes. Cubre los dos huecos de los pares actuales (adenda instructiva y eliminación de cláusula completa) con los mismos hechos esperados.

Borrador del contenido:

```text
ORIGINAL
1. Objeto. El Proveedor prestará servicios de mantenimiento.
2. Precio. El Cliente pagará USD 5.000 mensuales.
3. Penalidades. Cada día de demora generará una multa de USD 100.
4. Jurisdicción. Tribunales ordinarios de la Ciudad de Buenos Aires.

ENMIENDA
Las partes acuerdan:
a) Modificar la Cláusula 2, que quedará redactada así: "2. Precio. El Cliente pagará USD 5.500 mensuales."
b) Dejar sin efecto la Cláusula 3.
Las demás cláusulas permanecen vigentes.
```

- Tipo de enmienda esperado en el mapa: INSTRUCTIVA.
- `sections_changed` esperado: `Cláusula 2`, `Cláusula 3`.
- Hechos: `[MODIFICACIÓN]` Cláusula 2, USD 5.000 a USD 5.500; `[ELIMINACIÓN]` Cláusula 3 completa, eliminada expresamente.
- Sin cambios: Cláusulas 1 y 4, aunque la enmienda no las reproduzca. Si se reportan, es un error.
- No se espera ninguna `[ADICIÓN]`.
