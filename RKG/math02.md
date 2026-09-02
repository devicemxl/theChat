# Documento 2: Sincronización de fase (Kuramoto local)

## 1. Objetivo

La etapa de sincronización tiene como propósito filtrar el ruido semántico dentro del conjunto candidato \(C\) y descubrir subconjuntos coherentes. Para ello, modelamos cada nodo candidato como un oscilador de fase acoplado a sus vecinos dentro del subgrafo inducido por \(C\). Tras un número breve de iteraciones temporales, los osciladores que comparten frecuencias similares y están fuertemente conectados tienden a sincronizarse (sus fases se alinean), mientras que los nodos aislados o con frecuencias incompatibles permanecen desincronizados. La sincronización obtenida se traduce en una **matriz de coherencia \(S\)** que se usará en la etapa de propagación.

## 2. Modelo de osciladores acoplados en \(C\)

Sea \(C = \{i_1, i_2, \ldots, i_{k_c}\}\) el conjunto de candidatos recuperados por HNSW, con \(k_c = |C| = k_{\text{query}}\). Definimos el subgrafo inducido \(G_C = (C, E_C)\), donde

\[
E_C = \{ (i,j) \in E \mid i,j \in C \}
\]

es decir, solo se consideran las aristas cuya ambos extremos pertenecen a \(C\).

### 2.1 Ecuación de evolución de fase

Cada nodo \(i \in C\) tiene una fase \(\theta_i(t)\) que evoluciona según la ecuación de Kuramoto con acoplamiento heterogéneo:

\[
\frac{d\theta_i}{dt} = \omega_i + \sum_{j \in \mathcal{N}_i^C} K_{ij} \sin\left( \theta_j - \theta_i \right)
\]

donde:

- \(\omega_i\) es la frecuencia natural del nodo \(i\), definida en el Documento 1.
- \(\mathcal{N}_i^C = \mathcal{N}_i \cap C\) es el conjunto de vecinos de \(i\) dentro del subgrafo candidato.
- \(K_{ij}\) es la fuerza de acoplamiento entre \(i\) y \(j\).

La condición inicial es:

\[
\theta_i(0) = 0 \quad \forall i \in C
\]

Es decir, todos los osciladores arrancan en fase cero. La sincronización emerge exclusivamente por la interacción dinámica durante la integración.

### 2.2 Fuerza de acoplamiento \(K_{ij}\)

La fuerza de acoplamiento debe reflejar dos factores:

1. **Similitud semántica** (peso de la arista \(w_{ij}\), ya definido).
2. **Compatibilidad de frecuencias**: si dos nodos tienen frecuencias naturales muy distintas, su acoplamiento efectivo debe debilitarse, dificultando la sincronización.

Por tanto, definimos:

\[
K_{ij} = K \cdot w_{ij} \cdot \exp\left( -\alpha \left( \omega_i - \omega_j \right)^2 \right)
\]

donde:

- \(K > 0\) es la **constante de acoplamiento global**.
- \(w_{ij}\) es el peso de la arista (Documento 1).
- \(\alpha \ge 0\) es un parámetro que controla la selectividad por frecuencia. Si \(\alpha = 0\), se recupera el acoplamiento puramente basado en la similitud semántica. Si \(\alpha > 0\), los pares con frecuencias muy diferentes se acoplan débilmente, favoreciendo la formación de bloques sincronizados por frecuencia.

**Observación**: Dado que las frecuencias derivan de los embeddings (según Documento 1), este mecanismo ayuda a separar nodos de regiones semánticas distintas, incluso si el HNSW los ha mezclado como vecinos.

### 2.3 Normalización por grado

Para evitar que nodos con muchos vecinos dentro de \(C\) dominen la dinámica, normalizamos la suma por el número de vecinos:

\[
\frac{d\theta_i}{dt} = \omega_i + \frac{1}{|\mathcal{N}_i^C|} \sum_{j \in \mathcal{N}_i^C} K_{ij} \sin\left( \theta_j - \theta_i \right)
\]

Si \(|\mathcal{N}_i^C| = 0\), el nodo no recibe acoplamiento y su fase simplemente avanza linealmente: \(\theta_i(t) = \omega_i t\). Esto asegura que nodos aislados en el subgrafo candidato no se sincronizan artificialmente.

### 2.4 Propiedades del sistema

- **Simetría**: \(K_{ij} = K_{ji}\), porque \(w_{ij} = w_{ji}\) y la función exponencial es simétrica en la diferencia de frecuencias.
- **Acotación**: \(0 \le K_{ij} \le K \cdot \max(w_{ij})\).
- **Conservación de la fase media**: si todas las \(\omega_i\) son iguales, la dinámica converge a sincronización completa (\(\theta_i \to \theta_j\)). En general, la dinámica tiende a agrupar osciladores con frecuencias similares.

## 3. Integración numérica (método de Euler)

Elegimos un paso de integración \(\Delta t\) pequeño y ejecutamos \(T_{\text{sync}}\) pasos. Actualizamos las fases de forma síncrona:

```text
Inicializar θ_i = 0 para todo i ∈ C
Para t = 1, 2, ..., T_sync:
    δ_i = 0 para todo i ∈ C
    Para cada i ∈ C:
        Para cada j ∈ N_i^C:
            δ_i += K_ij * sin(θ_j - θ_i)
        δ_i /= |N_i^C|      # si |N_i^C| > 0, sino δ_i = 0
    Para cada i ∈ C:
        θ_i ← θ_i + Δt * (ω_i + δ_i)
```

### 3.1 Estabilidad y elección de \(\Delta t\)

Para que la integración sea estable, se requiere que \(\Delta t\) sea suficientemente pequeño comparado con la escala temporal del sistema. Una cota heurística es:

\[
\Delta t \le \frac{0.1}{\max_i \left( \omega_i + \sum_j K_{ij} \right)}
\]

En la práctica, con frecuencias \(\omega_i \in [0.5, 1.5]\) y \(K\) moderado (≤ 5), un paso \(\Delta t = 0.1\) es seguro. Si se observa divergencia, se reduce \(\Delta t\) o se limita el valor absoluto del incremento de fase.

### 3.2 Número de iteraciones \(T_{\text{sync}}\)

Típicamente \(T_{\text{sync}}\) entre 10 y 30 es suficiente para que emerjan estructuras de sincronización local. No es necesario alcanzar la sincronización completa; solo interesa la **coherencia relativa** entre pares de nodos, que se captura en la matriz \(S\) definida a continuación.

## 4. Medida de sincronización (matriz \(S\))

Al finalizar la integración, para cada par \((i,j)\) que sean vecinos en \(E_C\) (es decir, arista existente entre candidatos), definimos la medida de sincronización \(S_{ij}\) como:

\[
S_{ij} = w_{ij} \cdot \frac{1 + \cos(\theta_i - \theta_j)}{2}
\]

### 4.1 Interpretación

- Si \(\theta_i \approx \theta_j\), entonces \(\cos(\Delta\theta) \approx 1\) y \(S_{ij} \approx w_{ij}\): los nodos están fuertemente sincronizados y la arista transmite toda su influencia semántica.
- Si \(|\theta_i - \theta_j| = \pi\), entonces \(\cos(\Delta\theta) = -1\) y \(S_{ij} = 0\): la arista no transmite nada; los nodos están en oposición de fase.
- Valores intermedios dan una modulación suave entre 0 y \(w_{ij}\).

### 4.2 Propiedades de \(S_{ij}\)

- **Simetría**: \(S_{ij} = S_{ji}\).
- **No negatividad**: \(S_{ij} \ge 0\).
- **Acotación**: \(0 \le S_{ij} \le w_{ij} \le 1\).
- **Esparsidad heredada**: \(S_{ij} = 0\) si \((i,j) \notin E_C\). Por tanto, \(S\) es una matriz dispersa con la misma estructura de aristas que el subgrafo candidato.

### 4.3 Caso de pares no conectados

Para pares \(i,j\) que no están conectados por una arista en \(E_C\), definimos \(S_{ij} = 0\). Esto asegura que la propagación de activación (Documento 3) solo ocurra a través de aristas existentes.

## 5. Complejidad computacional

La sincronización implica, en cada iteración, para cada nodo \(i \in C\), sumar sobre sus vecinos en \(C\). El número de aristas en \(E_C\) es como mucho \(k_c \cdot \bar{d}_C\), donde \(\bar{d}_C\) es el grado medio en \(C\). En el peor caso denso, \(\bar{d}_C \approx k_c\), dando coste \(O(k_c^2)\) por iteración. Con \(k_c\) típicamente entre 20 y 100, esto es negligible en CPU.

La construcción de la matriz \(S\) requiere calcular \(\theta_i - \theta_j\) para cada arista en \(E_C\), coste \(O(|E_C|)\). También despreciable.

## 6. Parámetros y recomendaciones iniciales

| Parámetro | Símbolo | Valor sugerido | Observación |
|-----------|---------|----------------|-------------|
| Constante global de acoplamiento | \(K\) | 1.0 – 2.0 | Ajustar según el grado de coherencia deseado. |
| Selectividad por frecuencia | \(\alpha\) | 1.0 | Con frecuencias en [0.5,1.5], \(\alpha=1\) da decaimiento moderado. |
| Paso temporal | \(\Delta t\) | 0.1 | Estable para los rangos típicos. |
| Iteraciones de sincronización | \(T_{\text{sync}}\) | 20 | Suficiente para capturar coherencia. |

---

Con esto queda definida la etapa de sincronización. La matriz \(S\) resultante será utilizada como **matriz de propagación** en el Documento 3, donde describiremos la difusión de activación a través del subgrafo expandido \(R = C \cup \mathcal{N}(C)\).
