# **Contexto y Objetivos**

Imagina que trabajas como AI Engineer en una **empresa de tecnología legal (LegalMove)** que procesa miles de enmiendas de contratos cada mes.

Actualmente, el equipo de Compliance (Cumplimiento Legal) pasa más de 40 horas a la semana comparando manualmente los contratos originales con sus enmiendas (adendas) para identificar qué cambió, evaluar el impacto legal y derivar los documentos para su revisión. Este proceso manual es muy lento, propenso a errores humanos y un cuello de botella que impide escalar el negocio.

Tu misión es construir un Agente Autónomo de Comparación de Contratos. Este sistema recibirá las imágenes escaneadas de ambos documentos, las leerá utilizando IA de visión, y utilizará un equipo de "analistas virtuales" (Agentes de IA) para entender el contexto y extraer exactamente qué cláusulas se modificaron, devolviendo un reporte estructurado y sin errores que los sistemas de la empresa puedan procesar automáticamente.

### **🎯 Objetivo**

Desarrollar un **sistema multi-agente autónomo** que procese imágenes escaneadas de un contrato original y su adenda. El sistema deberá extraer el texto utilizando modelos fundacionales multimodales (Visión) y, mediante la colaboración de dos agentes especializados, identificar, extraer y resumir los cambios legales aplicados. El resultado final debe ser un formato estructurado (JSON) estrictamente validado, con trazabilidad completa de cada paso del proceso para garantizar su uso en entornos de producción.

### **⚙️ Stack técnico**

* **OpenAI GPT-4o (Vision)** → para parsear las imágenes de contratos y convertirlas en texto estructurado.  
* **LangChain** → para implementar y orquestar los dos agentes colaborativos.  
* **Pydantic** → para validar y estructurar el output final del sistema.  
* **Langfuse** → para instrumentar el trazado completo del workflow (image parsing, ejecución de agentes, validación).  
* **Python \+ python-dotenv** → como lenguaje base y manejo seguro de variables de entorno.

### **⚙️ Consigna  resumen**

Crear una aplicación en Python que reciba dos imágenes (contrato original y adenda). El sistema deberá usar un LLM Multimodal para leer los documentos y pasarlos por un flujo de dos agentes: uno que entiende el contexto y estructura del documento, y otro que extrae las diferencias. La salida del sistema debe ser un JSON validado por Pydantic que contenga las secciones modificadas, los temas legales afectados y un resumen preciso de los cambios. Todas las llamadas a la API y acciones de los agentes deben quedar registradas en un dashboard de Langfuse.

### **⚙️ Consigna técnica (pasos o etapas)**

**Paso 1 \- Parsing multimodal de imágenes**  
Implementar una función `parse_contract_image()` que reciba el path de una imagen (JPEG/PNG), la codifique en base64 y realice una llamada a la API de GPT-4o con capacidad multimodal. El prompt de visión debe instruir al modelo a extraer el texto completo del contrato de la forma más fiel posible. Este paso debe ejecutarse dos veces: una para el contrato original y otra para la enmienda. La observabilidad de estas ejecuciones (inputs, outputs, latencia y tokens) debe registrarse mediante spans de Langfuse dentro del pipeline principal (main).

**Paso 2 \- Agente 1: Contextualización**  
Implementar `ContextualizationAgent`, cuya responsabilidad es recibir los dos textos parseados y producir un análisis de estructura comparada: identificar qué secciones existen en ambos documentos, cómo se corresponden entre sí y cuál es el propósito general de cada bloque. El output del agente puede ser texto estructurado (no necesariamente JSON) que funcione como mapa contextual para el siguiente agente. Este agente no extrae cambios; solo construye el contexto necesario para el análisis posterior.

**Paso 3 – Agente 2: Extracción de cambios**  
Implementar `ExtractionAgent`, que recibe como input el output del Agente 1 (el mapa contextual) junto con ambos textos, y tiene la responsabilidad exclusiva de identificar, aislar y describir cada cambio introducido por la enmienda. Debe distinguir entre adiciones, eliminaciones y modificaciones. Su output debe ser un JSON estructurado con los tres campos requeridos, listo para ser validado por Pydantic.

**Paso 4 – Validación con Pydantic**  
Definir el modelo `ContractChangeOutput` con los campos:

* `sections_changed: List[str]` — identificadores de secciones modificadas.  
* `topics_touched: List[str]` — categorías legales/comerciales afectadas.  
* `summary_of_the_change: str` — descripción detallada de los cambios.

El output del Agente 2 debe cumplir este schema y ser validado utilizando Pydantic. Esto puede implementarse mediante validación explícita `(model_validate())` o mediante structured outputs usando r`esponse_format=ContractChangeOutput.`

**Paso 5 – Trazabilidad con Langfuse**  
Instrumentar el pipeline con trazabilidad usando Langfuse.

Se recomienda implementar un span raíz que represente la ejecución completa del pipeline y spans hijos para cada etapa principal.

Una posible estructura es:

`contract-analysis`

`├── parse_original_contract`

`├── parse_amendment_contract`

`├── contextualization_agent`

`└── extraction_agent`

Cada span debe incluir información relevante como input, output, latencia y metadata útil para debugging o auditoría.

# **Entregables del proyecto y requisitos de entrega**

### **📦 Entregables**

El proyecto se entrega mediante un **repositorio público de GitHub** que contiene:

| Entregable | Archivo | Descripción |
| :---- | :---- | :---- |
| Script principal | `src/main.py` | Entry point que acepta dos paths de imágenes como argumentos y ejecuta el pipeline completo |
| Agente 1 | `src/agents/contextualization_agent.py` | Agente de contextualización con system prompt y lógica propios |
| Agente 2 | `src/agents/extraction_agent.py` | Agente de extracción con system prompt y lógica propios |
| Utilidades de imagen | `src/image_parser.py` | Funciones de validación, encoding y llamadas multimodales |
| Modelos Pydantic | `src/models.py` | Modelo ContractChangeOutput con los tres campos requeridos |
| Imágenes de prueba | `data/test_contracts/` | Mínimo 2 pares de contratos (4 imágenes) con README explicativo |
| README | `README.md` | Documentación completa con diagramas, arquitectura, setup, uso y decisiones técnicas |
| Dependencias | `requirements.txt` \+ `.env.example` | Dependencias con versiones fijadas y template de variables de entorno |
| Integración Langfuse | Instrumentación del pipeline principal con una traza que agrupe las etapas del análisis. | Traces con jerarquía de spans para cada etapa del pipeline |

# **Defensa en vivo (instancia final)**

En lugar de un video pregrabado, se realizará una **sesión en vivo** de presentación y defensa técnica del proyecto (durante 30 minutos).

Durante la sesión, deberás:

* Presentar brevemente el contexto de la empresa LegalMove y el problema que el sistema resuelve.  
* Mostrar el pipeline en funcionamiento con al menos dos pares de contratos: un caso con cambios simples (una cláusula modificada) y uno con cambios complejos (múltiples secciones afectadas).  
* Explicar en el dashboard de Langfuse cómo se ve la traza completa de una ejecución: los spans, los inputs/outputs de cada agente y las métricas de tokens y latencia.  
* Responder preguntas del corrector sobre decisiones técnicas (ejm) por qué dos agentes en lugar de uno, por qué GPT-4o para el parsing, cómo se diseñaron los system prompts y cómo se maneja la validación de errores.

# **Recursos adicionales**

### **Contratos de prueba simulados**

Para los pares de contratos de prueba podés:

* Utilizar los archivos ya generados: [Recursos adicionales](https://drive.google.com/drive/folders/1JGZmR0UiJLvs1yxoh6VhWUnfm8FaidSw)  
* O generar tus propios documentos PDF simples con herramientas como Canva, Google Docs o Word, exportarlos como imágenes. Podes evaluar los siguientes escenarios:

**→ Par 1** (cambios simples): Contrato de servicios donde la enmienda modifica únicamente el monto mensual y la fecha de vencimiento.

**→ Par 2** (cambios complejos): Contrato de confidencialidad donde la enmienda agrega una cláusula nueva, modifica el alcance territorial y elimina una restricción de uso.

### **OpenAI Vision: Análisis de imágenes**

* Documentación oficial: [Images and vision \| OpenAI API](https://developers.openai.com/api/docs/guides/images-vision?format=base64-encoded#analyze-images) 

**Setup de Langfuse**

* Crear cuenta en cloud.langfuse.com.  
* Crear un nuevo proyecto y obtener `LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY.`  
* Instalar con `pip install langfuse.`  
* Inicializar el cliente con las keys desde variables de entorno.

Variables de entorno requeridas (.env.example)

* `OPENAI_API_KEY=your-key-here`  
* `LANGFUSE_PUBLIC_KEY=pk-lf-xxx`  
* `LANGFUSE_SECRET_KEY=sk-lf-xxx`  
* `LANGFUSE_HOST=https://cloud.langfuse.com`

# **Rúbrica de evaluación**

La evaluación de este proyecto se centra en su capacidad para orquestar **modelos fundacionales multimodales (Visión)** y flujos de trabajo con **agentes especializados**. Se calificará con rigor la precisión en la extracción de texto de documentos originales y sus adendas, así como la efectividad de la colaboración entre agentes para identificar y resumir cambios legales. La rúbrica validará que el sistema no solo funcione, sino que produzca un **JSON estructurado y estrictamente validado**, garantizando que la salida posea la trazabilidad necesaria para un entorno de producción real.

A diferencia de módulos anteriores donde la revisión era asíncrona, esta vez la **evaluación será en vivo y bajo la modalidad 1 a 1**. Durante esta sesión de defensa individual, un corrector validará en tiempo real el funcionamiento de su solución y la lógica detrás de cada agente implementado. Deberán demostrar un dominio técnico total para justificar la elección de sus modelos y la robustez de su sistema ante casos de prueba. El éxito en esta dinámica depende de la coherencia técnica de su arquitectura y de su agilidad para explicar paso a paso cómo garantizan la integridad de los datos extraídos.

### **¿Qué funciones específicas vamos a evaluar?**

Durante la sesión, el evaluador pondrá especial atención en los siguientes componentes de su arquitectura:

* **Capacidad de Visión:** Calidad y fidelidad del texto extraído de las imágenes/PDFs de contratos y adendas.  
* **Orquestación de Agentes:** Lógica de colaboración y especialización de los dos agentes en el flujo de trabajo.  
* **Validación de Salida:** Integridad y estructura del esquema **JSON** generado (debe ser estrictamente funcional para producción).  
* **Trazabilidad y Logs:** Evidencia clara de cada paso del proceso, permitiendo auditar cómo se llegó al resumen final.

**Por favor, revisa a continuación la rúbrica detallada para conocer cada indicador y asegurar que su proyecto cumple con el nivel de excelencia requerido.**

| Criterio | Excelente (100%) | Satisfactorio (75%) | Insatisfactorio (0-50%) | Puntaje |
| :---- | :---- | :---- | :---- | :---- |
| **1\. FUNCIONALIDAD & REQUISITOS CORE** |  |  |  |  |
| 1.1 Parsing Multimodal | Implementa parse\_contract\_image() con GPT-4o Vision y base64. Extrae texto con precisión respetando jerarquías (cláusulas/secciones). | El parsing funciona pero pierde parte de la jerarquía o formato del documento original. | No usa visión (solo OCR tradicional). El parsing obtenido tiene mucho ruido y el texto obtenido no es preciso. | 15 |
| 1.2 Arquitectura de 2 Agentes | Separación clara entre ContextualizationAgent y ExtractionAgent. Existe un flujo de handoff lógico donde el segundo usa el mapa del primero. | Ambos agentes existen pero sus responsabilidades se solapan o el traspaso de información es redundante/ineficiente. | Solo hay un agente "monolítico" o los agentes no colaboran (corren de forma independiente sin compartir contexto). | 15 |
| 1.3 Validación Pydantic | El output final cumple estrictamente el modelo ContractChangeOutput y se valida utilizando Pydantic (mediante model\_validate() o structured outputs con response\_format). Maneja excepciones de validación con elegancia y mensajes claros. | Define el modelo Pydantic pero el flujo no siempre garantiza la validación o faltan descripciones de campo/tipado. | No utiliza Pydantic para validar la salida final o el modelo no incluye los 3 campos obligatorios solicitados. | 10 |
| **2\. IMPLEMENTACIÓN TÉCNICA Y PROMPTING** |  |  |  |  |
| 2.1 Calidad del Prompting | System prompts altamente especializados para cada agente (Analista Senior vs Auditor). | Prompts funcionales pero genéricos. No se aprovecha el rol del sistema para mejorar la precisión del análisis legal. | Prompts muy pobres o instrucciones ambiguas que generan alucinaciones frecuentes en la extracción de cambios. | 15 |
| 2.2 Gestión de API y Errores | Manejo robusto de errores de API (timeouts, límites de tokens) y de codificación de imágenes. Uso correcto de variables de entorno. | Implementa manejo de errores básico (try/except genérico). Algunas claves o configuraciones están hardcodeadas. | El código se rompe ante errores de API o falta el archivo .env.example. No hay validación de entrada de archivos. | 10 |
| **3\. OBSERVABILIDAD (LANGFUSE)** |  |  |  |  |
| 3.1 Trazabilidad del Workflow | Traza padre con jerarquía clara de spans. Registra inputs, outputs y métricas relevantes (latencia, tokens u otra metadata disponible) para cada etapa del pipeline. | Registra la ejecución en Langfuse pero de forma plana (sin jerarquía de spans) o faltan métricas críticas de tokens/costo. | No hay integración con Langfuse o las trazas están incompletas (solo registra el paso final, por ejemplo). | 15 |
| **4\. CALIDAD DE CÓDIGO Y DOCUMENTACIÓN** |  |  |  |  |
| 4.1 Estructura y README | Código modular (POO o funcional limpio). README excelente con diagrama de arquitectura, instrucciones de setup y justificación técnica. | Código funcional pero desorganizado (archivos muy largos). README básico con instrucciones mínimas de instalación. | Repositorio desordenado. Sin README o sin instrucciones claras para que el corrector pueda ejecutar el proyecto. | 10 |
| **5\. DEFENSA TÉCNICA EN VIVO** |  |  |  |  |
| 5.1 Presentación y Demo | Explica con fluidez decisiones de diseño. Muestra el dashboard de Langfuse y justifica el uso de agentes. Demo exitosa con 2 casos. | Realiza la demo pero le cuesta explicar la lógica detrás de los agentes o no sabe interpretar las métricas en Langfuse. | No puede ejecutar la demo en vivo o no comprende el flujo de datos entre los componentes de su propio sistema. | 10 |
|  |  |  |  |  |
|  |  |  | **PUNTAJE TOTAL** | 100 |

