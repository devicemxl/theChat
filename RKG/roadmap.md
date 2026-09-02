# Roadmap Final del Proyecto RKG

## 1. Contexto y estado actual

- **Documentación completada**: README conceptual, definición matemática exhaustiva (Documentos 1–4) y arquitectura de software.
- **Licencia**: Cerrada (uso privado, no open source).
- **Stack tecnológico**: Python 3.10+, `hnswlib`, `sqlite3`, `numpy`.
- **Embeddings**: Gemma 300M.
- **Objetivo**: Construir un MVP funcional de RKG que mejore la recuperación de contexto para RAG mediante sincronización, propagación y memoria.

Actualmente no existe código; se parte de las especificaciones escritas.

---

## 2. Fases del proyecto

### Fase 0: Preparación del entorno y esqueleto del repositorio

**Objetivo**: Crear la estructura básica del proyecto, definir los parámetros globales y sentar las bases para la implementación.

**Tareas**:
- Crear estructura de directorios según el documento de arquitectura.
- Implementar `config.py` con todos los parámetros por defecto (valores sugeridos en documentos matemáticos).
- Preparar un archivo `requirements.txt` (hnswlib, numpy, scipy opcional).
- Configurar entorno virtual y control de versiones.

**Entregables**:
- Repositorio con carpetas `src/`, `tests/`, `docs/`.
- `config.py` con parámetros documentados.
- Entorno de desarrollo funcional.

**Criterios de aceptación**:
- Se puede importar `config` y acceder a todos los parámetros.
- No hay errores de importación al ejecutar un script dummy.

**Dependencias**: Ninguna.

**Tiempo estimado**: 0.5 semana.

---

### Fase 1: Infraestructura base (HNSW + SQLite + búsqueda simple)

**Objetivo**: Implementar el almacenamiento persistente, el índice vectorial y la búsqueda semántica clásica (HNSW-RAG básico).

**Tareas**:
1. Implementar clase `Database`:
   - Crear tablas `nodes` y `edges`.
   - Métodos para insertar nodos (con embeddings serializados) y aristas.
   - Métodos para obtener nodos por IDs y todas las aristas.
   - Método para actualizar energía (por ahora, solo campo).
2. Implementar clase `HNSWIndex`:
   - Envolver `hnswlib.Index`.
   - Construcción del índice a partir de embeddings y IDs.
   - Carga/guardado del índice en disco.
   - Búsqueda de `k` vecinos.
3. Implementar script `build_index.py`:
   - Recibir un corpus (lista de textos o embeddings precalculados).
   - Generar embeddings (si se proporcionan textos) con el modelo elegido (Gemma 300M o MiniLM).
   - Insertar nodos en SQLite.
   - Construir índice HNSW.
   - Extraer aristas del propio HNSW (vecinos de cada nodo) y almacenarlas en `edges` con pesos.
4. Implementar script `query.py` de prueba:
   - Dado un texto de consulta, generar embedding.
   - Buscar en HNSW y devolver los `k` nodos más cercanos con su metadata.
5. Probar con un corpus pequeño (sintético o una muestra de documentos).

**Entregables**:
- `database.py`, `hnsw_index.py`, `graph.py` (parcial: carga de aristas).
- Scripts `build_index.py` y `query.py` funcionales.
- Base SQLite poblada e índice HNSW guardado.

**Criterios de aceptación**:
- Se puede construir el índice con al menos 1.000 nodos.
- La búsqueda devuelve resultados coherentes (vecinos cercanos).
- Las aristas se guardan correctamente con pesos.
- La consulta tarda < 10 ms para `k=50`.

**Dependencias**: Fase 0.

**Tiempo estimado**: 1–2 semanas.

---

### Fase 2: Sincronización de fase y propagación

**Objetivo**: Añadir la capa dinámica de RKG: sincronización Kuramoto local y propagación de activación.

**Tareas**:
1. Implementar `graph.py` completo:
   - Cargar en memoria todos los embeddings, aristas y frecuencias naturales (calculadas con PCA o proyección fija).
   - Métodos para obtener vecinos y pesos.
2. Implementar `sync.py`:
   - Función `synchronize(candidate_ids, ...)` que ejecuta la dinámica de Kuramoto (Euler explícito) y devuelve fases `theta` y matriz `S`.
   - Construcción de matriz `S` para aristas internas de `C`.
3. Implementar `propagate.py`:
   - Función `build_conductance_matrix(R, C, S, weights)`.
   - Función `propagate_activation(R, L, a_init, epsilon, T_prop)` (difusión normalizada con ReLU).
4. Implementar `memory.py`:
   - Función `update_energy(activations, current_energies, lambda, gamma, E_max)`.
   - Integración con `Database.update_energy_batch`.
5. Crear clase `RKG` (orquestador) en `pipeline.py`:
   - Método `query(query_embedding)` que ejecuta el ciclo completo (candidate search, inicialización, sincronización, expansión R, construcción L, propagación, readout, actualización de energía).
6. Actualizar script `query.py` para que use el pipeline completo.
7. Pruebas unitarias para `sync`, `propagate`, `memory`.

**Entregables**:
- Módulos `sync.py`, `propagate.py`, `memory.py`, `pipeline.py` completos.
- Pipeline `RKG.query` funcional que devuelve contexto expandido.
- Tests unitarios para las funciones matemáticas.

**Criterios de aceptación**:
- Dado un conjunto candidato, la sincronización produce fases coherentes para pares de alta similitud/frecuencia y baja para pares disonantes.
- La propagación expande la activación a vecinos directos pero no más allá (limitado a un salto).
- La actualización de energía persiste y se refleja en consultas posteriores.
- El pipeline completo se ejecuta sin errores con un corpus de prueba.
- Tiempo de consulta < 50 ms para `k_query=50`, `T_sync=20`, `T_prop=5`.

**Dependencias**: Fase 1.

**Tiempo estimado**: 2–3 semanas.

---

### Fase 3: Memoria persistente y ajustes de parámetros

**Objetivo**: Refinar la memoria de energía, integrar sesgo de energía en la activación inicial y ajustar parámetros para mejorar la calidad.

**Tareas**:
1. Modificar la activación inicial para incluir la energía persistente:
   \[
   a_i(0) = \exp(-\|\mathbf{e}_i-\mathbf{e}_q\|^2/\sigma_q^2) \cdot (1 + \beta E_i)
   \]
   con \(\beta\) un nuevo parámetro (por defecto 0.1).
2. Implementar poda de nodos obsoletos (fuera de línea, script aparte):
   - Nodos con energía por debajo de umbral durante N consultas se marcan como inactivos.
   - No se eliminan físicamente, solo se excluyen de futuras búsquedas HNSW (filtro en SQL).
3. Ajustar empíricamente los parámetros \(K, \alpha, \lambda, \gamma, \tau, \varepsilon\) usando un conjunto de validación con queries y documentos relevantes (métricas: recall@k, MRR).
4. Añadir logging y métricas básicas de rendimiento (tiempos por etapa, número de nodos activos).

**Entregables**:
- Memoria de energía integrada en la activación inicial.
- Script de poda (`prune.py`) con heurística simple.
- Configuración de parámetros refinada para un dataset de prueba.
- Reporte breve de métricas de evaluación inicial.

**Criterios de aceptación**:
- La energía acumulada influye positivamente en la recuperación (mejora recall en consultas repetidas).
- La poda reduce el espacio de búsqueda sin perder calidad.
- Se documentan los valores de parámetros óptimos encontrados.

**Dependencias**: Fase 2.

**Tiempo estimado**: 2 semanas.

---

### Fase 4: Evaluación y optimización

**Objetivo**: Medir el rendimiento y la calidad del contexto generado por RKG frente a un baseline de HNSW-RAG clásico.

**Tareas**:
1. Definir un benchmark de evaluación:
   - Usar un corpus con preguntas y documentos relevantes (ej. subconjunto de Wikipedia en español, o dataset sintético).
   - Métricas: Recall@k, MRR, precisión de contexto.
2. Implementar script `eval.py` que ejecute consultas con RKG y con búsqueda HNSW pura, y compare resultados.
3. Realizar experimentos de ablación:
   - Sin sincronización (usar solo \(S = w\)).
   - Sin propagación (solo candidatos HNSW).
   - Sin memoria (energía reiniciada en cada consulta).
4. Optimizar código:
   - Vectorizar cálculos con NumPy.
   - Reducir accesos a SQLite (caché de embeddings y aristas).
   - Ajustar parámetros de HNSW (`M`, `ef`).
5. Documentar resultados en un informe breve.

**Entregables**:
- Script de evaluación funcional.
- Resultados comparativos (tablas/gráficos).
- Versión optimizada del código.
- Informe de ablación con conclusiones.

**Criterios de aceptación**:
- RKG obtiene un Recall@10 al menos igual o superior al baseline HNSW en al menos un 5% en el benchmark.
- El tiempo de respuesta no supera el doble del baseline.
- Se identifican los componentes que aportan mayor mejora (sincronización o propagación).

**Dependencias**: Fase 3.

**Tiempo estimado**: 2–3 semanas.

---

### Fase 5 (futuro): Escalabilidad y características adicionales

**Objetivo**: Preparar el sistema para producción con mayores volúmenes de datos y funcionalidades avanzadas (no incluidas en MVP).

**Posibles tareas**:
- Migración de HNSW a una solución distribuida (FAISS con sharding).
- Uso de memoria mapeada (mmap) para embeddings.
- Implementación de actualización incremental del índice HNSW.
- Incorporación de un grafo semántico adicional (relaciones explícitas) combinado con el grafo HNSW.
- Aprendizaje de frecuencias \(\omega_i\) mediante optimización.
- Integración con un servidor de API (FastAPI) para consultas remotas.
- Implementación de RL heurístico para mantenimiento del grafo (solo si se valida la necesidad).

**Nota**: Esta fase no tiene un cronograma definido; se abordará según los resultados y necesidades reales.

---

## 3. Cronograma resumido

| Fase | Duración estimada | Entregable principal |
|------|-------------------|----------------------|
| 0: Preparación | 0.5 semanas | Estructura y configuración |
| 1: Infraestructura base | 1–2 semanas | HNSW + SQLite + búsqueda |
| 2: Sincronización y propagación | 2–3 semanas | Pipeline RKG funcional |
| 3: Memoria persistente y ajustes | 2 semanas | Memoria integrada, poda |
| 4: Evaluación y optimización | 2–3 semanas | Benchmark y conclusiones |
| **Total MVP** | **7–10 semanas** | Sistema RKG evaluado |

---

## 4. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| La sincronización no aporta mejoras claras | Media | Alto | Probar con diferentes parámetros; comparar con baseline simple. Si no mejora, reconsiderar modelo. |
| Coste de propagación excesivo al crecer \(k_{\text{query}}\) | Media | Medio | Limitar expansión a un salto; optimizar con matrices dispersas. |
| Embeddings de Gemma 300M no disponibles o costosos de generar | Baja | Alto | Usar modelo alternativo (MiniLM) para validar la arquitectura; luego migrar. |
| HNSW pierde eficacia al añadir nodos | Media (a largo plazo) | Medio | Reconstruir índice periódicamente; usar parámetros adecuados; explorar otros índices (FAISS). |
| Sesgo de memoria demasiado fuerte | Media | Medio | Ajustar \(\beta\) y \(\lambda\); permitir decaimiento rápido. |

---

## 5. Criterios de finalización del MVP

El MVP se considera completado cuando:

- Se puede construir el índice y la base de datos a partir de un corpus.
- El pipeline RKG responde consultas en < 50 ms (sin contar generación de embedding).
- La propagación expande el contexto de manera coherente.
- La memoria de energía persiste y afecta a recuperaciones posteriores.
- Se ha realizado una evaluación comparativa con HNSW-RAG clásico.
- Los resultados muestran que RKG mejora al menos una métrica de recuperación sin degradar significativamente el rendimiento.
