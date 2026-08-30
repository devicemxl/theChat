# Documento de Diseño: Ciclo Agéntico para Chat App con Herramientas

## 1. Introducción

Este documento describe el diseño de un **ciclo agéntico** (agent loop) para tu aplicación de chat multi‑proveedor. El objetivo es permitir que el modelo de lenguaje (LLM) interactúe con el entorno del proyecto: explorar archivos, leer contenido y escribir archivos, todo bajo restricciones estrictas de seguridad y con un flujo de aprobación humana.

El middleware en Python será el encargado de ejecutar las herramientas solicitadas por el modelo, actuando como puente entre la interfaz de usuario, el LLM y el sistema de archivos/git.

---

## 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Streamlit)                  │
│  - UI de chat                                               │
│  - Selector de modo (chat / code)                           │
│  - Visualización de pasos del agente                        │
│  - Botón de aprobación de cambios                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Middleware / Backend (Python)                 │
│  - Gestión del ciclo agéntico                               │
│  - Comunicación con APIs de LLM                             │
│  - Ejecución de herramientas (validación + sandbox)         │
│  - Persistencia de herramientas y resultados                │
│  - Respaldo automático con git (commits locales)            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│        Herramientas (File System, Git read-only)           │
│  - listar_directorio                                        │
│  - buscar_archivo                                           │
│  - buscar_contenido                                         │
│  - leer_archivo                                             │
│  - escribir_archivo                                         │
│  - git_status / git_diff / git_log                          │
└─────────────────────────────────────────────────────────────┘
```

El **frontend** solo recibe el resultado final del agente y permite al usuario aprobar o rechazar cambios. El **middleware** controla todo el ciclo y ejecuta las herramientas de forma aislada y segura.

---

## 3. Herramientas Definidas

Cada herramienta se describe mediante un esquema (nombre, descripción, parámetros) que se envía al LLM para que este pueda solicitar su ejecución.

### 3.1 Exploración

- **`listar_directorio(ruta, max_resultados=50)`**  
  Devuelve las entradas inmediatas (archivos y subdirectorios) de una ruta dada, con metadatos básicos (tipo, tamaño, extensión). Filtra automáticamente carpetas y archivos irrelevantes (venv, __pycache__, node_modules, .git, binarios, etc.). El resultado se pagina si supera `max_resultados`.

- **`buscar_archivo(patron, ruta_raiz=".", max_resultados=100)`**  
  Busca archivos por nombre o patrón glob (ej. `*.odin`, `main.*`). Aplica los mismos filtros de exclusión. Devuelve lista de rutas relativas.

- **`buscar_contenido(texto, ruta_raiz=".", extensiones=None, max_resultados=50)`**  
  Realiza una búsqueda de texto (grep) en archivos permitidos. Devuelve rutas, números de línea y fragmentos con contexto. Ideal para localizar símbolos, funciones o errores.

### 3.2 Lectura

- **`leer_archivo(ruta, inicio=None, fin=None)`**  
  Devuelve el contenido de un archivo de texto (o un rango de líneas). Solo admite extensiones permitidas (txt, md, odin, go, c, json, py, etc.). La ruta debe estar dentro del proyecto y no puede ser un archivo binario o reservado (`.env`, `.git`, etc.).

### 3.3 Escritura

- **`escribir_archivo(ruta, contenido)`**  
  Crea o sobrescribe un archivo de texto. Valida que la ruta esté dentro del directorio del proyecto y que la extensión sea permitida. No permite escribir en archivos ocultos ni en directorios de sistema. Devuelve confirmación o error.

### 3.4 Git (solo lectura)

- **`git_status()`**  
  Ejecuta `git status --porcelain` y devuelve el estado de los archivos (modificados, nuevos, eliminados).

- **`git_diff(scope="working_tree")`**  
  Devuelve el diff del working tree o del índice (`--cached`). Permite al modelo ver los cambios actuales.

- **`git_log(max_commits=10)`**  
  Devuelve un listado de los últimos commits (`git log --oneline -N`), útil para contexto histórico.

- **Restricción:** no se permite ningún subcomando que modifique el repositorio (`commit`, `push`, `pull`, `checkout`, `merge`, `rebase`, `stash`, `add`, `rm`, etc.). Solo lectura garantizada por una lista blanca.

---

## 4. Ciclo Agéntico Paso a Paso

1. **Entrada del usuario**  
   El usuario escribe un mensaje. Según el modo seleccionado (chat o code), el sistema decide si se activa el agente completo o solo se responde de forma conversacional.

2. **Preparación del contexto**  
   Se compone el historial de mensajes, incluyendo llamadas a herramientas previas y sus resultados (si las hay). Se añade un *system prompt* que describe la tarea, las herramientas disponibles y las reglas de uso.

3. **Llamada al LLM**  
   Se envía la solicitud al proveedor seleccionado (DeepSeek, Mistral, Gemini) con la definición de herramientas habilitadas. La API puede devolver:
   - Una **respuesta normal** (texto): el agente ha terminado.
   - Una o varias **tool calls**: el modelo solicita ejecutar una herramienta con ciertos argumentos.

4. **Ejecución de herramientas**  
   Si hay tool calls:
   - El middleware valida cada llamada (seguridad, tipos, permisos).
   - Ejecuta la herramienta correspondiente.
   - Captura el resultado (éxito, error, salida formateada).
   - Añade al historial un mensaje con la llamada y su resultado.

5. **Continuación del ciclo**  
   Se vuelve al paso 3 con el historial enriquecido. El modelo puede pedir más herramientas o dar la respuesta final. Se limita el número máximo de iteraciones (por ejemplo, 10) para evitar bucles infinitos.

6. **Respuesta final**  
   Cuando el modelo responde con texto normal, se considera que el ciclo terminó. El frontend muestra la respuesta al usuario, junto con un registro de las herramientas utilizadas (opcional, en un expander).

7. **Aprobación de cambios**  
   Si en modo code se realizaron escrituras, se muestra al usuario un resumen (git diff) y botones para **aprobar** (commit + push) o **rechazar** (revertir al snapshot anterior).

---

## 5. Adaptación Multi‑Proveedor

Cada proveedor implementa function calling de forma ligeramente diferente. El middleware debe abstraer estas diferencias:

- **DeepSeek**: formato similar a OpenAI. Las herramientas se envían en un parámetro `tools` y el modelo devuelve `tool_calls` con `id`, `name` y `arguments` (JSON string).
- **Mistral AI**: también compatible con OpenAI Chat Completions API; se puede usar el mismo esquema de `tools` y `tool_calls`.
- **Google Gemini**: usa un formato distinto (`function_declarations`) y devuelve `functionCall` en sus respuestas.

El middleware traducirá las definiciones de herramientas al formato de cada proveedor y normalizará las respuestas a una estructura interna común. Además, gestionará el *streaming*: durante la generación de tool calls, es posible que el proveedor devuelva los argumentos en trozos; el middleware deberá reconstruirlos antes de ejecutar la herramienta.

---

## 6. Integración con Streamlit

- **Selección de modo**: un dropdown en la sidebar (`💬 Chat` / `💻 Code`) determina si el agente puede ejecutar herramientas. En modo chat, las herramientas no se envían al LLM.
- **Visualización de pasos**: durante el ciclo, se muestra un indicador de actividad. Si se desea, cada herramienta ejecutada se registra en un `st.expander` dentro del mensaje del asistente, revelando la llamada y el resultado.
- **Aprobación**: después de la respuesta final en modo code, se muestra un bloque con el resumen de cambios (usando `git_diff`) y botones `✅ Aprobar y hacer push` / `❌ Descartar`. El backend ejecuta las acciones correspondientes (commit y push, o reset al snapshot).
- **Persistencia**: el historial en SQLite debe almacenar las tool calls y resultados como mensajes especiales para conservar el contexto al recargar la conversación. Si el usuario aprueba, se puede añadir un mensaje de sistema indicando el commit realizado.

---

## 7. Gestión de Contexto y Límites

- El historial enviado al LLM debe incluir **solo la información relevante**. Las herramientas de exploración están diseñadas para que el modelo pida datos acotados, evitando el volcado masivo de archivos.
- Se establece un **límite de iteraciones** (por defecto 10) para el ciclo agéntico.
- Se limita el **número de herramientas por turno** (por ejemplo, el modelo puede pedir varias a la vez, pero si es demasiado ambicioso se pueden encolar).
- El sistema puede **truncar resultados largos** (como /dev/null) y ofrecer al modelo la posibilidad de paginar o refinar la búsqueda.
- Se incluye un *system prompt* que instruye al modelo a explorar de forma incremental y no solicitar más de lo necesario.

---

## 8. Seguridad

### 8.1 Validación de Rutas

- Toda ruta pasada a herramientas de lectura/escritura se **normaliza** (resuelve `..`, symlinks) y se verifica que la ruta absoluta resultante esté **dentro de la raíz del proyecto**.
- Se mantiene una **lista de archivos/directorios prohibidos** (`.env`, `.git/config`, claves, etc.) que nunca pueden ser leídos ni escritos.
- Las escrituras solo permiten extensiones de texto plano; se rechazan binarios.

### 8.2 Git de Solo Lectura

- Se utiliza una **lista blanca de subcomandos** y se ejecuta `git` mediante `subprocess` con argumentos como lista (no string) para evitar inyección.
- Cualquier comando no permitido devuelve un error controlado.

### 8.3 Aislamiento

- Para máxima seguridad, el ciclo agéntico se ejecuta sobre un **directorio de trabajo aislado**. Opcionalmente se puede usar un contenedor Docker o un entorno virtual por proyecto.
- Antes de que el agente comience a modificar, se realiza un **commit de respaldo automático** (`snapshot before LLM`) para poder revertir fácilmente.

### 8.4 Permisos del Usuario

- El usuario debe **activar explícitamente el modo code** para habilitar las herramientas de escritura.
- Las operaciones que afectan al repositorio remoto (`push`) solo se ejecutan tras la aprobación manual del usuario.

---

## 9. Estrategia de Respaldo con Git

1. **Inicio de sesión code**: el backend verifica que el directorio es un repositorio git.
2. **Antes de cada interacción del agente** (si va a usar herramientas de escritura): el middleware ejecuta `git add -A && git commit -m "snapshot before LLM <timestamp>"` de forma automática. Esto crea un punto limpio.
3. **El agente trabaja** (escribe archivos, consulta git status, etc.).
4. **El usuario evalúa** los cambios (diff en la UI).
5. **Si aprueba**:
   - Se ejecuta `git add -A` y `git commit` (mensaje generado por el LLM o manual).
   - Se ejecuta `git push` al remoto configurado.
6. **Si rechaza**:
   - Se puede revertir al snapshot anterior conservando el commit de respaldo, o simplemente descartar los cambios no confirmados (`git checkout -- .`).
   - Se informa al usuario de la acción tomada.

---

## 10. Listado de Archivos Filtrado

Para que el agente explore el proyecto sin ruido, el middleware implementa un walker personalizado que:

- Ignora directorios y archivos definidos en una **lista de exclusión** (venv, __pycache__, node_modules, .git, build, dist, .idea, etc.).
- Ignora archivos ocultos sensibles (`.env`, `.gitignore`, claves).
- Se apoya en `.gitignore` si existe, pero no depende de él.
- Filtra archivos binarios (por extensión o por contenido) para no devolver basura.
- Devuelve resultados paginados y con metadatos simples.

Este listado se usa en `listar_directorio`, `buscar_archivo` y `buscar_contenido`, garantizando consistencia.

---

## 11. Manejo de Errores y Reintentos

- Si una herramienta falla (ruta inválida, permiso denegado, archivo binario), se devuelve un mensaje de error al LLM, que puede decidir corregir la llamada o cambiar de estrategia.
- El middleware registra todos los errores para depuración.
- Se puede permitir un reintento automático limitado (por ejemplo, el modelo puede volver a pedir la misma herramienta con argumentos corregidos) sin intervención del usuario.

---

## 12. Consideraciones Futuras

- **Herramienta de ejecución de comandos** (tests, builds) con sandbox Docker y lista blanca de comandos.
- **Índice semántico** para búsquedas por embeddings en proyectos muy grandes.
- **Modos de aprobación granular** (aprobar solo algunos archivos).
- **Historial de snapshots** y capacidad de comparar versiones intermedias.
