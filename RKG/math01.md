Licencia cerrada, perfecto. Lo omitimos del README y seguimos.

---

## Propuesta de división en documentos matemáticos

Para no dejar cabos sueltos y tener una base completa antes de tocar código, propongo dividir la definición matemática en **cuatro documentos encadenados**:

1. **Documento 1 — Fundamentos y notación**  
   Definición del espacio de conocimiento, grafo HNSW, embeddings, frecuencias naturales, estado persistente y dinámico, parámetros globales.  
   *Aquí se fijan todos los símbolos, estructuras de datos y suposiciones.*

2. **Documento 2 — Sincronización de fase (Kuramoto local)**  
   Ecuaciones de acoplamiento, integración temporal, matriz de sincronización \(S_{ij}\), justificación geométrica y propiedades.

3. **Documento 3 — Propagación de activación y memoria**  
   Difusión normalizada sobre el subgrafo expandido, actualización de energía persistente, criterios de convergencia y umbrales de readout.

4. **Documento 4 — Algoritmo completo de consulta y pseudocódigo**  
   Integración de todas las etapas en un flujo ejecutable, con entradas, salidas y decisiones de implementación.

¿Te parece bien? Si es así, comenzamos ahora con el **Documento 1**.

---

# Documento 1: Fundamentos y notación

## 1. Espacio del conocimiento

Sea \(\Omega\) el espacio de embeddings semánticos de dimensión \(d\). Consideramos un conjunto finito de nodos \(V\), donde cada nodo \(i \in V\) posee:

- **Embedding estático** \( \mathbf{e}_i \in \Omega \subset \mathbb{R}^d \)
- **Metadatos** \( m_i \) (texto, tipo, fuente, etc.)
- **Identificador único** \( \text{id}_i \)

El conjunto \(V\) constituye la **memoria persistente** del sistema. No cambia durante una consulta (excepto por actualización explícita de energía, que es estado dinámico persistente).

## 2. Grafo de conocimiento a partir de HNSW

El grafo \(G = (V, E, w)\) se construye a partir del índice HNSW.

### 2.1 Construcción del índice HNSW

Se genera un índice HNSW sobre todos los embeddings \( \mathbf{e}_i \). El índice define, para cada nodo \(i\), una lista de vecinos aproximados \(\text{Neigh}_{\text{HNSW}}(i, M)\) donde \(M\) es el número máximo de conexiones por capa (parámetro de construcción del HNSW).

### 2.2 Derivación del grafo

Para \(k_{\text{graph}}\) un parámetro fijo (por ejemplo, \(k_{\text{graph}} = 16 \)), definimos el grafo no dirigido \(G\) mediante:

\[
E = \{ (i,j) \mid j \in \text{Neigh}_{\text{HNSW}}(i, k_{\text{graph}}) \; \text{or} \; i \in \text{Neigh}_{\text{HNSW}}(j, k_{\text{graph}}) \}
\]

Si el HNSW es jerárquico, se puede considerar solo la capa base (capa 0) para las aristas. Para simplicidad, asumimos que el HNSW devuelve vecinos de la capa base.

### 2.3 Pesos de las aristas

Definimos el peso de una arista \((i,j) \in E\) usando similitud coseno entre embeddings:

\[
w_{ij} = \frac{\langle \mathbf{e}_i, \mathbf{e}_j \rangle}{\|\mathbf{e}_i\| \|\mathbf{e}_j\|}
\]

con \(w_{ij} \in [-1, 1]\). Para evitar pesos negativos en la dinámica, aplicamos una transformación afín o un umbral:

\[
w_{ij} = \max(0, \cos(\mathbf{e}_i, \mathbf{e}_j))
\]

o alternativamente:

\[
w_{ij} = \exp\left( - \frac{\|\mathbf{e}_i - \mathbf{e}_j\|^2}{\sigma^2} \right)
\]

Elegimos la función exponencial para asegurar \(w_{ij} \in (0,1]\), con \(\sigma\) un parámetro de escala (por ejemplo, la desviación estándar de las distancias en el grafo). Denotamos \(\sigma_w\) para evitar conflicto con \(\sigma_q\) usado más adelante.

### 2.4 Propiedades del grafo

- \(w_{ij} = w_{ji}\) (simetría).  
- \(w_{ij} > 0\) para aristas existentes.  
- El grafo es disperso: \(d_{\text{avg}} \approx 2k_{\text{graph}}\).

## 3. Estado dinámico por nodo

Cada nodo \(i\) posee un conjunto de variables dinámicas que evolucionan durante una consulta:

| Variable | Símbolo | Tipo | Descripción |
|----------|---------|------|-------------|
| Fase | \(\theta_i(t)\) | escalar | Ángulo de oscilación, inicializado a 0 en cada consulta |
| Frecuencia natural | \(\omega_i\) | escalar | Derivada del embedding, fija por consulta (precalculable) |
| Activación | \(a_i(t)\) | escalar \(\ge 0\) | Nivel de activación/resonancia, inicializado según similitud con consulta |
| Energía persistente | \(E_i\) | escalar \(\ge 0\) | Acumula utilidad histórica; persiste entre consultas |

Opcionalmente, puede existir una variable **amplitud** \(A_i\) que modula la influencia en la propagación, pero en la versión MVP la absorbemos dentro de \(a_i\) o la definimos como función de \(E_i\):

\[
A_i = \log(1 + E_i)
\]

## 4. Frecuencia natural derivada del embedding

Para cada nodo \(i\), definimos su frecuencia natural \(\omega_i \in \mathbb{R}\) como una proyección del embedding a un escalar:

\[
\omega_i = \omega_{\text{center}} + \Delta\omega \cdot \tanh\left( \mathbf{w}_\omega^\top \mathbf{e}_i + b_\omega \right)
\]

donde:

- \(\mathbf{w}_\omega \in \mathbb{R}^d\) es un vector de proyección. En la versión no aprendida, se puede tomar como la **primera componente principal** de los embeddings de \(V\) (calculada con PCA), o un vector aleatorio normalizado. En versiones aprendidas, se puede optimizar.
- \(b_\omega\) es un sesgo, típicamente 0.
- \(\omega_{\text{center}}\) y \(\Delta\omega\) son parámetros que centran y escalan el rango de frecuencias. Por ejemplo, \(\omega_{\text{center}} = 1.0\), \(\Delta\omega = 0.5\), dando \(\omega_i \in [0.5, 1.5]\).

La tangente hiperbólica asegura que \(\omega_i\) esté acotada. Esta acotación es importante para la estabilidad de la sincronización.

## 5. Vector de consulta y activación inicial

Dada una consulta \(q\), se calcula su embedding \(\mathbf{e}_q \in \Omega\).

### 5.1 Candidate Search

Se recupera el conjunto de candidatos \(C \subset V\) como los \(k_{\text{query}}\) vecinos más cercanos en el índice HNSW:

\[
C = \text{HNSW\_query}(\mathbf{e}_q, k_{\text{query}})
\]

con \(k_{\text{query}}\) típicamente entre 20 y 100.

### 5.2 Activación inicial

Para cada \(i \in C\), la activación inicial \(a_i(0)\) se define como una función de la similitud entre \(\mathbf{e}_q\) y \(\mathbf{e}_i\):

\[
a_i(0) = \exp\left( - \frac{\|\mathbf{e}_i - \mathbf{e}_q\|^2}{\sigma_q^2} \right)
\]

donde \(\sigma_q\) controla la escala de similitud. Para nodos \(i \notin C\), \(a_i(0) = 0\).

Esta activación inicial sirve como "semilla" para la propagación posterior.

## 6. Parámetros globales

| Símbolo | Significado | Valor sugerido |
|---------|-------------|----------------|
| \(d\) | Dimensión del embedding | 384 (MiniLM) o 300 (Gemma 300M) |
| \(M\) | Conexiones por nodo en HNSW | 16 |
| \(k_{\text{graph}}\) | Vecinos para construir grafo | 16 |
| \(k_{\text{query}}\) | Candidatos HNSW por consulta | 50 |
| \(\sigma_w\) | Ancho del kernel de pesos de aristas | ~0.5 · distancia media |
| \(\sigma_q\) | Ancho del kernel de activación inicial | ~0.5 · distancia media |
| \(\omega_{\text{center}}\) | Centro de frecuencia | 1.0 |
| \(\Delta\omega\) | Rango de frecuencia | 0.5 |
| \(K\) | Acoplamiento global en Kuramoto | 0.5 – 2.0 |
| \(\Delta t\) | Paso de integración temporal | 0.1 |
| \(T_{\text{sync}}\) | Iteraciones de sincronización | 20 |
| \(\varepsilon\) | Coeficiente de difusión | 0.5 |
| \(T_{\text{prop}}\) | Iteraciones de propagación | 5 |
| \(\lambda\) | Factor de decaimiento de energía | 0.9 |
| \(\gamma\) | Ganancia de energía por activación | 1.0 |
| \(\tau\) | Umbral relativo de activación para readout | 0.1 – 0.3 |

Estos valores son orientativos y deben ajustarse experimentalmente.

## 7. Funciones auxiliares y convenciones

- \(\mathcal{N}_i\) denota el conjunto de vecinos de \(i\) en el grafo \(G\).
- \(\mathcal{N}_i^{\cap C}\) denota los vecinos de \(i\) que también están en el conjunto candidato \(C\).
- \(\|\cdot\|\) es la norma euclidiana.
- \(\langle\cdot,\cdot\rangle\) es el producto interno.
