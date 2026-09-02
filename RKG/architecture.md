# Documento de Arquitectura Propuesta

## 1. Propósito

Este documento describe la arquitectura software del **Resonant Knowledge Graph (RKG)**, cubriendo la organización de componentes, persistencia, interfaces internas y flujo de ejecución. El objetivo es proporcionar una guía clara para la implementación del MVP en Python, con las bibliotecas `hnswlib`, `sqlite3` y `numpy`.

La arquitectura se basa en los fundamentos y ecuaciones definidos en los documentos matemáticos (1–4), y no introduce nuevos conceptos matemáticos; se limita a especificar cómo se implementan.

## 2. Vista general de componentes

El sistema se compone de los siguientes módulos principales, que se comunican entre sí mediante llamadas directas en el proceso:

```
+-------------------+
|   Orquestador     |
|  (Pipeline de     |
|    consulta)      |
+---------+---------+
          |
          v
+---------+---------+      +---------------------+
|  Índice HNSW      |<---->|  Base de datos SQLite|
|  (hnswlib)        |      |  (nodes, edges,     |
+---------+---------+      |   dynamic_state)    |
          |               +---------------------+
          v
+---------+---------+
|  Grafo en memoria |
|  (numpy arrays)   |
+---------+---------+
          |
          v
+---------+---------+
|  Sincronización   |
|  (Kuramoto local) |
+---------+---------+
          |
          v
+---------+---------+
|  Propagación      |
|  de activación    |
+---------+---------+
          |
          v
+---------+---------+
|  Memoria/Energía  |
+-------------------+
```

Cada módulo es una clase o conjunto de funciones con responsabilidades claras.

## 3. Descripción detallada de componentes

### 3.1 Índice HNSW

**Responsabilidad**: Mantener el índice de búsqueda vectorial aproximada y permitir consultas de vecinos cercanos.

**Implementación**: Clase `HNSWIndex` que envuelve `hnswlib.Index`.

**Datos almacenados**:
- `index` (instancia de hnswlib)
- `path` del archivo de índice (si se persiste en disco)
- `dim` (dimensión de embeddings)
- `max_elements` (número máximo de nodos)

**Métodos principales**:
- `load(path)`: carga índice desde archivo.
- `build(embeddings, ids)`: construye índice a partir de array de embeddings.
- `search(query_embedding, k)`: devuelve `(ids, distancias)` de los k vecinos más cercanos.
- `save(path)`: guarda el índice a disco.

**Notas**:
- El índice se construye una vez con todos los embeddings; luego se usa en modo lectura.
- Si se añaden nodos posteriormente (fuera del MVP), se requiere reconstrucción o inserción incremental (hnswlib soporta `add_items`).

### 3.2 Base de datos SQLite

**Responsabilidad**: Persistencia de la información estática (nodos, aristas, embeddings) y del estado dinámico persistente (energía).

**Implementación**: Clase `Database` que maneja la conexión y las consultas.

**Esquema de tablas** (según Documento 1):

```sql
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    embedding BLOB NOT NULL,      -- vector serializado (float32)
    metadata TEXT,                -- JSON con texto, tipo, etc.
    energy REAL DEFAULT 0.0       -- energía persistente
);

CREATE TABLE IF NOT EXISTS edges (
    src INTEGER NOT NULL,
    dst INTEGER NOT NULL,
    weight REAL NOT NULL,         -- peso de arista (w_ij)
    PRIMARY KEY (src, dst)
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
```

**Opcionalmente** se puede usar una tabla separada para estado dinámico:

```sql
CREATE TABLE IF NOT EXISTS dynamic_state (
    id INTEGER PRIMARY KEY,
    energy REAL DEFAULT 0.0,
    last_update TIMESTAMP
);
```

Para el MVP, mantenemos la energía en la tabla `nodes` por simplicidad.

**Métodos principales**:
- `get_nodes_by_ids(ids)`: devuelve embeddings, metadata y energía para un conjunto de ids.
- `get_edges_for_subgraph(node_ids)`: devuelve aristas con peso donde `src` o `dst` estén en `node_ids`.
- `get_all_edges()`: carga todas las aristas (si el grafo cabe en memoria, recomendado).
- `update_energy_batch(updates)`: recibe lista de `(id, nueva_energia)` y ejecuta `UPDATE` en una transacción.
- `close()`: cierra conexión.

**Notas**:
- Los embeddings se almacenan como BLOB (serializados con `numpy.tobytes()`).
- Para rendimiento, se recomienda cargar todas las aristas en memoria al inicio y reconstruir listas de vecindades; las consultas a SQLite solo se usan para obtener embeddings y actualizar energía.

### 3.3 Grafo en memoria

**Responsabilidad**: Mantener la estructura del grafo (nodos y aristas) de forma eficiente para acceso rápido durante las consultas.

**Implementación**: Clase `Graph` o estructura simple con arrays de numpy.

**Datos en memoria**:
- `adj_list`: diccionario `{node_id: [neighbor_ids]}` o listas de adyacencia.
- `weights`: diccionario `{(src,dst): weight}` o matriz dispersa.
- `embeddings`: diccionario `{node_id: np.array}` (o array global indexado por posición).
- `freqs`: diccionario `{node_id: omega}` o array global.

Para evitar uso excesivo de RAM con embeddings grandes, se puede mantener los embeddings en disco y cargar solo los necesarios. En el MVP, asumimos que el número de nodos es manejable para cargar todos los embeddings en memoria (por ejemplo, < 100k nodos de dimensión 300).

**Métodos principales**:
- `load_from_database(db)`: construye `adj_list`, `weights`, `embeddings`, `freqs`.
- `get_neighbors(node_id)`: devuelve vecinos.
- `get_weight(i,j)`: devuelve peso de arista.

**Notas**:
- Las frecuencias \(\omega_i\) se calculan una vez al cargar el grafo (según Documento 1) y se almacenan en memoria. No cambian entre consultas.

### 3.4 Módulo de sincronización

**Responsabilidad**: Implementar la dinámica de Kuramoto local sobre un conjunto candidato \(C\).

**Implementación**: Clase `Synchronizer` o funciones en `sync.py`.

**Entradas**:
- `C`: lista de ids de nodos candidatos.
- `adj_list`, `weights` (para subgrafo inducido \(E_C\)).
- `freqs`: frecuencias de los candidatos.
- Parámetros: `K`, `alpha`, `dt`, `T_sync`.

**Salida**:
- `theta`: diccionario con fases finales por nodo.
- `S`: matriz de sincronización (diccionario o matriz numpy dispersa) para pares en \(E_C\).

**Métodos**:
- `synchronize(C, ...) -> (theta, S)`.

**Notas**:
- La sincronización se realiza solo entre candidatos. No se cargan vecinos externos en este módulo.
- La matriz \(S\) se puede construir como un diccionario anidado o como `scipy.sparse` si se desea optimizar.

### 3.5 Módulo de propagación

**Responsabilidad**: Expandir la activación desde \(C\) hacia vecinos directos y propagar usando la matriz \(L\).

**Implementación**: Clase `Propagator` o funciones en `propagate.py`.

**Entradas**:
- `R`: lista de nodos en subgrafo de expansión.
- `C`: subconjunto de R.
- `L`: matriz de conductancia construida a partir de \(S\) y pesos de aristas.
- `a_init`: activaciones iniciales.
- Parámetros: `epsilon`, `T_prop`.

**Salida**:
- `a`: diccionario con activaciones finales para nodos en R.

**Métodos**:
- `propagate(R, C, L, a_init, epsilon, T_prop) -> a`.

**Notas**:
- La matriz \(L\) se construye en este módulo o en un helper aparte.
- Para eficiencia, se puede usar numpy arrays y operaciones vectorizadas; sin embargo, con tamaños pequeños (|R| ~ 200-500) los bucles son aceptables.

### 3.6 Módulo de memoria/energía

**Responsabilidad**: Actualizar la energía persistente de los nodos y proporcionar consultas de energía.

**Implementación**: Clase `Memory` o funciones en `memory.py`.

**Entradas**:
- `a`: activaciones finales.
- `energies`: energías actuales.
- Parámetros: `lambda`, `gamma`, `E_max`.

**Salida**:
- `updates`: lista de `(id, nueva_energia)` para actualizar en SQLite.

**Métodos**:
- `update_energy(activations, current_energies) -> updates`.

**Notas**:
- La actualización se ejecuta en una sola transacción SQLite.
- No se guarda el historial de energía; solo el valor actual.

### 3.7 Orquestador (Pipeline de consulta)

**Responsabilidad**: Coordinar todos los módulos para ejecutar el ciclo completo de consulta.

**Implementación**: Clase `RKG` con método `query(embedding, params)`.

**Método `query`**:
1. Llama a `HNSWIndex.search` para obtener candidatos \(C\).
2. Llama a `Database.get_nodes_by_ids` para cargar embeddings, energía actual.
3. Calcula activaciones iniciales (según Documento 1).
4. Llama a `Synchronizer.synchronize` para obtener `theta` y `S`.
5. Llama a `Graph.get_neighbors` para cada candidato y construye \(R\).
6. Construye matriz \(L\) (puede ser un helper).
7. Llama a `Propagator.propagate` para obtener activaciones finales.
8. Determina contexto (aplicando umbral relativo).
9. Llama a `Memory.update_energy` para calcular nuevas energías.
10. Llama a `Database.update_energy_batch` para persistir.
11. Devuelve contexto (lista de nodos con metadata, activación, energía).

## 4. Flujo de ejecución de una consulta (diagrama de secuencia textual)

```
Cliente -> RKG.query(e_q)
  RKG -> HNSWIndex.search(e_q, k) -> C
  RKG -> Database.get_nodes_by_ids(C) -> embeddings, energies
  RKG calcula a_i(0)
  RKG -> Synchronizer.synchronize(C, ...) -> theta, S
  RKG -> Graph.get_neighbors(C) -> vecinos para R
  RKG construye L (helper)
  RKG -> Propagator.propagate(R, C, L, a_init) -> a_final
  RKG -> Memory.update_energy(a_final, energies) -> updates
  RKG -> Database.update_energy_batch(updates)
  RKG aplica umbral y ordena contexto
  RKG retorna contexto
```

## 5. Estructura de directorios y archivos

Siguiendo la propuesta del README:

```
rkg/
├── README.md
├── docs/
│   ├── modelo_matematico_1_fundamentos.md
│   ├── modelo_matematico_2_sincronizacion.md
│   ├── modelo_matematico_3_propagacion_memoria.md
│   ├── modelo_matematico_4_algoritmo.md
│   ├── arquitectura.md
│   └── roadmap.md
├── src/
│   ├── rkg/
│   │   ├── __init__.py
│   │   ├── config.py           # definición de parámetros y constantes
│   │   ├── database.py         # clase Database (SQLite)
│   │   ├── hnsw_index.py       # clase HNSWIndex
│   │   ├── graph.py            # clase Graph (estructura en memoria)
│   │   ├── sync.py             # funciones de sincronización
│   │   ├── propagate.py        # funciones de propagación
│   │   ├── memory.py           # funciones de actualización de energía
│   │   ├── pipeline.py         # clase RKG (orquestador)
│   │   └── utils.py            # helpers (cálculo de omega, activación inicial, etc.)
│   └── scripts/
│       ├── build_index.py      # construir HNSW y poblar SQLite
│       ├── query.py            # script de prueba de consulta
│       └── eval.py             # evaluación simple
└── tests/
    ├── test_database.py
    ├── test_graph.py
    ├── test_sync.py
    └── test_propagate.py
```

## 6. Decisiones de diseño y justificación

### 6.1 Separación de módulos por etapas del pipeline

Cada etapa matemática (sincronización, propagación, memoria) es un módulo separado, lo que permite:

- Probar cada etapa de forma aislada.
- Reemplazar o mejorar una etapa sin afectar a las demás (por ejemplo, cambiar la dinámica de Kuramoto por otra).
- Mantener el código legible.

### 6.2 Uso de SQLite como almacenamiento principal

- Permite persistencia transaccional.
- No requiere servidor externo.
- El grafo se reconstruye en memoria para acelerar consultas.

### 6.3 Carga completa del grafo en memoria

Para volúmenes moderados (hasta ~100k nodos con embeddings de 300 dims), el costo de memoria es aceptable (~120 MB para embeddings + listas de adyacencia). Esto evita consultas constantes a SQLite durante la sincronización y propagación.

Si el grafo crece más, se puede migrar a una solución con memoria mapeada o bases de datos vectoriales puras (FAISS, etc.).

### 6.4 No usar un motor de grafos especializado

La malla aplanada (tablas `nodes` y `edges`) es suficiente para reconstruir las vecindades. Un motor de grafos (Neo4j, etc.) añadiría complejidad innecesaria en el MVP.

### 6.5 Activación inicial basada solo en similitud con la consulta

La energía persistente no se utiliza aún para sesgar la activación inicial en el MVP, pero se deja la puerta abierta (por ejemplo, multiplicar \(a_i(0)\) por \(1 + \beta E_i\)). Se implementará en fases posteriores.

## 7. Interacción con el exterior

**Entrada del sistema**:
- Embedding de consulta \(e_q\) (vector de dimensión \(d\)).
- Parámetros de consulta (opcional, por defecto los globales).

**Salida del sistema**:
- Lista de nodos relevantes, cada uno con:
  - `id`
  - `metadata` (texto u otros)
  - `activation` (valor final \(a_i\))
  - `energy` (valor actual \(E_i\))

El consumidor puede ser un modelo de lenguaje, un sistema de recuperación, o simplemente una API.

## 8. Consideraciones de rendimiento y escalabilidad

### 8.1 Tiempos esperados por consulta (estimación)

Con \(k_{\text{query}}=50\), \(d=300\), grafo con \(N=100k\) nodos:

- Búsqueda HNSW: ~0.1 ms
- Sincronización (20 iteraciones, ~100 aristas internas): < 1 ms
- Propagación (5 iteraciones, ~800 aristas): < 5 ms
- Actualización SQLite (transacción): ~1-5 ms
- Total: ~10-20 ms por consulta (sin contar generación de embedding).

Esto es aceptable para aplicaciones de RAG interactivas.

### 8.2 Uso de RAM

Aproximadamente:

- Embeddings: \(N \times d \times 4\) bytes (float32). Para \(N=100k, d=300\): ~120 MB.
- Listas de adyacencia: \(N \times \text{grado} \times 4\) bytes. Con grado medio 16: ~6.4 MB.
- Índice HNSW: ~\(N \times M \times 4\) bytes. Similar a las adyacencias.
- Total: ~150 MB. Perfectamente asumible.

### 8.3 Escalabilidad

- Se puede reducir la memoria cargando embeddings desde disco bajo demanda (mmap).
- Para grafos de millones de nodos, se recomienda migrar a un índice distribuido (FAISS con sharding) y mantener el estado dinámico en Redis o similar.
- La sincronización y propagación son locales a la región candidata, por lo que el costo no escala con \(N\), solo con \(k_{\text{query}}\) y el grado medio.

## 9. Próximos pasos

1. Implementar `config.py` con parámetros por defecto.
2. Implementar `database.py` y `hnsw_index.py`.
3. Implementar `graph.py` para cargar estructuras.
4. Implementar `sync.py`, `propagate.py`, `memory.py`.
5. Implementar `pipeline.py` que integre todo.
6. Crear scripts `build_index.py` y `query.py` para pruebas.
7. Probar con un corpus sintético (ej. 1000 documentos con embeddings aleatorios o MiniLM).
8. Evaluar calidad del contexto comparado con búsqueda HNSW simple.
