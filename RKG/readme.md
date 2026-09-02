# Resonant Knowledge Graph (RKG)

**RKG** es una capa de recuperación estructurada de conocimiento que combina búsqueda semántica aproximada (HNSW), dinámica de sincronización local (modelo de Kuramoto) y memoria persistente por nodos.

Su objetivo es mejorar la calidad del contexto recuperado para sistemas de RAG (Retrieval-Augmented Generation) y otras arquitecturas de inferencia, al añadir coherencia estructural, propagación contextual y memoria adaptativa a la búsqueda por embeddings.

---

## ¿Qué es RKG?

RKG es un sistema que opera sobre un **grafo persistente** construido a partir de un índice HNSW sobre embeddings semánticos. Cada nodo del grafo representa una unidad de conocimiento (documento, fragmento, concepto) y cada arista una relación de proximidad semántica.

A diferencia de un buscador semántico clásico que solo devuelve los K vecinos más cercanos, RKG ejecuta un **ciclo cognitivo** en cada consulta:

1. Recupera una región candidata del grafo mediante HNSW.
2. Inicializa el estado dinámico de los nodos candidatos.
3. Ejecuta una **sincronización local** entre nodos, permitiendo que emerjan subconjuntos coherentes.
4. Propaga la activación a través de las aristas del grafo, expandiendo la región relevante.
5. Actualiza una **memoria persistente** (energía) en los nodos que participaron.
6. Extrae el contexto final (subgrafo coherente) para ser usado por un LLM u otro consumidor.

RKG no reemplaza al modelo de lenguaje; actúa como una **capa intermedia entre la representación persistente del conocimiento y los motores de inferencia**.

---

## ¿Por qué RKG? (Motivación)

### Limitaciones del HNSW-RAG clásico

El flujo tradicional de RAG basado en búsqueda semántica tiene problemas bien conocidos:

- **Ambigüedad semántica**: los vecinos más cercanos por embedding pueden incluir ruido (significados múltiples, temas tangenciales).
- **Sin propagación**: si la respuesta requiere información que está a dos o más saltos del hit inicial, no se recupera.
- **Sin memoria**: cada consulta es independiente; el sistema no recuerda qué nodos fueron útiles en el pasado.
- **Sin estructura**: no se aprovechan las relaciones entre nodos para refinar la recuperación.

### Propósito de RKG

RKG aborda estas limitaciones mediante tres mecanismos:

- **Sincronización** para filtrar ruido y descubrir coherencia local entre candidatos.
- **Propagación** para expandir la región relevante siguiendo las aristas del grafo.
- **Memoria de energía** para acumular evidencia de utilidad de los nodos entre consultas.

El resultado esperado es un contexto de mayor calidad: más preciso, más completo y adaptativo a los patrones de uso.

---

## ¿Cómo funciona? (Alto nivel)

### Componentes principales

- **Grafo persistente**: Representado como una “malla aplanada” en SQLite (tablas de nodos y aristas). Las aristas provienen del índice HNSW construido sobre los embeddings.
- **Índice HNSW**: Proporciona acceso rápido a vecinos semánticos. Se construye con `hnswlib` sobre embeddings generados por un modelo (p. ej., Gemma 300M).
- **Estado dinámico por nodo**: Durante cada consulta, cada nodo candidato lleva variables temporales: fase (θ), frecuencia natural (ω) y activación (a). Además, posee una variable persistente: energía (E).
- **Sincronización local**: Los nodos candidatos interactúan como osciladores de fase acoplados (modelo de Kuramoto). La fuerza de acoplamiento depende de la similitud de frecuencias y de los pesos de las aristas. Tras un número breve de iteraciones, se obtiene una matriz de sincronización \(S\) que indica qué nodos son mutuamente coherentes.
- **Propagación de activación**: La activación inicial (basada en similitud con la consulta) se difunde a través de la matriz \(S\), alcanzando a nodos vecinos que no estaban en el conjunto candidato original. Esto permite descubrir “islas semánticas” más amplias.
- **Memoria persistente**: La energía de cada nodo se actualiza al final de cada consulta: crece si el nodo fue activado, decae lentamente en caso contrario. Esta memoria influye en consultas futuras (por ejemplo, sesgando la activación inicial o la poda de nodos obsoletos).
- **Salida**: El subgrafo activo final (nodos con activación superior a un umbral) se convierte en el contexto que se entrega a un LLM o sistema downstream.

### Flujo conceptual

```
Consulta → Embedding → HNSW → Candidatos → Sincronización → Propagación → Contexto
                                                          ↘
                                                        Memoria persistente
```

---

## Características clave

- **Recuperación estructurada**: No se limita a devolver los vecinos más cercanos; refina y expande la región coherente.
- **Coherencia por sincronización**: Los nodos ruidosos o poco relacionados tienden a no sincronizar y se descartan del contexto.
- **Propagación contextual**: La activación fluye por las aristas del grafo, incorporando nodos relacionados aunque no fueran candidatos iniciales.
- **Memoria adaptativa**: La energía persistente permite que el sistema “recuerde” qué nodos han sido históricamente útiles.
- **Independiente del LLM**: RKG produce contexto estructurado (lista de nodos con metadatos y activación), no respuestas directas. Puede integrarse con cualquier modelo generativo o sistema simbólico.
- **Persistencia sencilla**: Usa SQLite como base de datos relacional plana, sin necesidad de un motor de grafos especializado.

---

## Estado actual del proyecto

**Fase actual: MVP (fase 1 y 2)**

- [x] Diseño conceptual y matemático.
- [ ] Índice HNSW + SQLite con nodos y aristas.
- [ ] Búsqueda simple (HNSW-RAG clásico).
- [ ] Sincronización de fase (Kuramoto) sobre candidatos.
- [ ] Propagación de activación y extracción de contexto.
- [ ] Memoria de energía persistente (fase 3).
- [ ] Evaluación experimental y optimización.

Actualmente estamos implementando la **Fase 1** (infraestructura base) y la **Fase 2** (dinámica de sincronización/propagación).

---

## Tecnología

- **Lenguaje**: Python 3.10+
- **Índice vectorial**: `hnswlib`
- **Base de datos**: `sqlite3`
- **Álgebra**: `numpy` (posiblemente `scipy` para matrices dispersas)
- **Embeddings**: Gemma 300M (u otro modelo compatible, p. ej., `sentence-transformers`)

---

## Estructura sugerida del repositorio

```text
rkg/
├── README.md
├── docs/
│   ├── modelo_matematico.md
│   ├── arquitectura.md
│   └── roadmap.md
├── src/
│   ├── rkg/
│   │   ├── __init__.py
│   │   ├── graph.py          # manejo de nodos/aristas en SQLite
│   │   ├── hnsw_index.py     # construcción y búsqueda HNSW
│   │   ├── sync.py           # sincronización Kuramoto
│   │   ├── propagate.py      # propagación de activación
│   │   └── memory.py         # actualización de energía
│   └── scripts/
│       ├── build_index.py
│       ├── query.py
│       └── eval.py
└── tests/
    └── ...
```

---

## Instalación rápida (preliminar)

```bash
pip install hnswlib numpy
```

Uso básico (se completará con la implementación):

```python
from rkg import RKG

rkg = RKG(index_path="data/gemma.hnsw", db_path="data/rkg.db")

# Indexar documentos (una vez)
rkg.build_from_embeddings(embeddings, metadata)

# Consulta
context = rkg.query(query_embedding)
```

---

## Roadmap resumido

1. **Fase 1**: Infraestructura base (HNSW + SQLite + búsqueda simple).
2. **Fase 2**: Sincronización y propagación.
3. **Fase 3**: Memoria persistente y ajustes.
4. **Fase 4**: Evaluación y optimización.

Para más detalles, véase `docs/roadmap.md`.

---

## Contribución

Este proyecto está en desarrollo inicial. Se aceptan contribuciones, especialmente en los temas de:

- Optimización de la sincronización (paralelización con NumPy/CuPy).
- Alternativas de grafo semántico más robustas que HNSW puro.
- Métricas de evaluación para RAG en español.

---

## License

Personal project. No public license is offered at this time. If you want to
use the code, open an issue and let's talk.
