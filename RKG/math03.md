Perfecto, aquí tienes el **Documento 3** formalizado y consistente con los anteriores.

---

# Documento 3: Propagación de activación y memoria

## 1. Objetivo

Tras la sincronización local en el conjunto candidato \(C\), se obtiene una matriz de coherencia \(S\) que cuantifica la sincronización entre pares de nodos candidatos. La etapa de **propagación de activación** utiliza esta información para expandir la región activa desde \(C\) hacia sus vecinos directos en el grafo, permitiendo descubrir nodos relevantes que no fueron recuperados inicialmente por HNSW. Al finalizar la propagación, se actualiza una **memoria persistente** (energía) de los nodos participantes y se extrae el subgrafo de contexto final.

## 2. Definición del subgrafo de expansión \(R\)

Sea \(R\) el subgrafo inducido por los candidatos y sus vecinos directos:

\[
R = C \cup \bigcup_{i \in C} \mathcal{N}_i
\]

donde \(\mathcal{N}_i\) es el conjunto de vecinos de \(i\) en el grafo completo \(G\). Las aristas de \(R\) son todas aquellas de \(G\) con ambos extremos en \(R\):

\[
E_R = \{ (i,j) \in E \mid i,j \in R \}
\]

El subgrafo de trabajo para la propagación es \(G_R = (R, E_R)\).

## 3. Matriz de conductancia de aristas \(L\)

Para la propagación, necesitamos una matriz no negativa \(L\) que asigne una conductancia a cada arista de \(E_R\). Esta matriz combina la coherencia de sincronización para aristas entre candidatos y el peso semántico para aristas que involucran nodos fuera de \(C\).

Definimos:

\[
L_{ij} = \begin{cases}
S_{ij} & \text{si } i,j \in C \\
w_{ij} & \text{si } i \in C, j \notin C \text{ (o viceversa)} \\
0 & \text{si } i,j \notin C \text{ y } (i,j) \in E_R \text{ (opcional)}
\end{cases}
\]

**Justificación**:

- Para aristas entre candidatos, \(S_{ij}\) ya captura tanto la similitud semántica como la coherencia de fase obtenida en la sincronización.
- Para aristas entre un candidato y un vecino externo, no disponemos de información de fase del vecino (no participó en la sincronización), por lo que utilizamos el peso de la arista \(w_{ij}\) como conductancia. Esto permite que la activación fluya hacia vecinos semánticamente cercanos sin necesidad de sincronizarlos.
- Para aristas entre dos nodos externos, típicamente no propagamos activación entre ellos porque no queremos alejarnos demasiado del conjunto candidato. Por tanto, \(L_{ij}=0\) para esos pares, limitando la expansión a un solo salto desde \(C\). (Alternativamente, se podría permitir, pero para el MVP mantenemos solo un salto.)

**Nota**: Esta matriz \(L\) es dispersa y no negativa, heredando la estructura de \(E_R\).

## 4. Ecuación de propagación (difusión normalizada)

Sea \(a_i(t)\) la activación del nodo \(i\) en la iteración \(t\). Inicializamos las activaciones de la siguiente manera:

\[
a_i(0) = \begin{cases}
\exp\left( - \dfrac{\|\mathbf{e}_i - \mathbf{e}_q\|^2}{\sigma_q^2} \right) & \text{si } i \in C \\
0 & \text{si } i \in R \setminus C
\end{cases}
\]

Es decir, solo los candidatos tienen activación inicial proporcional a su similitud con la consulta. Los vecinos externos parten de cero y podrán activarse solo si reciben flujo de los candidatos.

La difusión se define de forma iterativa, normalizando por el grado ponderado para evitar divergencias:

\[
a_i(t+1) = \phi\left( (1-\varepsilon)\, a_i(t) + \varepsilon \cdot \frac{ \sum_{j \in R} L_{ij} \, a_j(t) }{ \sum_{j \in R} L_{ij} } \right)
\]

donde:

- \(\varepsilon \in (0,1)\) es el coeficiente de mezcla entre el valor actual y la influencia de los vecinos (coeficiente de difusión). Típicamente \(\varepsilon = 0.5\).
- \(\phi\) es una función de activación no lineal. Se propone \(\phi(x) = \max(0, x)\) (ReLU) para evitar valores negativos, o \(\phi(x) = \tanh(x)\) para acotar en \([0,1]\). Para el MVP se usará ReLU.
- Si \(\sum_{j} L_{ij} = 0\) (nodo sin aristas en \(R\)), el término del vecindario se anula y \(a_i(t+1) = \phi((1-\varepsilon)a_i(t))\).

La iteración se repite durante \(T_{\text{prop}}\) pasos (típicamente 5).

**Interpretación**: Esta es una difusión normalizada en grafo (similar a una red GCN), que permite que la activación fluya desde los candidatos hacia sus vecinos, pero con una retención parcial \((1-\varepsilon)\) que evita la sobreexpansión y mantiene la señal original.

### 4.1 Propiedades de la ecuación

- La matriz de transición efectiva es \(P = (1-\varepsilon) I + \varepsilon D^{-1} L\), donde \(D\) es la matriz diagonal con \(D_{ii} = \sum_j L_{ij}\). Si \(L\) es no negativa y cada fila tiene suma finita, \(P\) es estocástica (por filas), garantizando que las activaciones no crecen sin control.
- Con \(\phi = \text{ReLU}\), las activaciones se mantienen no negativas.
- El número de iteraciones \(T_{\text{prop}}\) controla el alcance de la propagación; para \(T_{\text{prop}}=5\), la influencia llega aproximadamente hasta 5 saltos, pero en la práctica se limita a los vecinos directos de \(C\) porque los nodos externos no tienen aristas entre sí (ver \(L_{ij}=0\) para aristas externas). Por tanto, la expansión efectiva es de un salto desde \(C\).

## 5. Memoria persistente: actualización de energía

Cada nodo \(i \in V\) posee una variable de **energía** \(E_i\), que persiste entre consultas y se almacena en SQLite (tabla `dynamic_state`). Tras finalizar la propagación, se actualiza la energía de los nodos en \(R\) (o de todos los nodos con activación positiva) según la regla:

\[
E_i \leftarrow \text{clamp}\left( \lambda\, E_i + \gamma\, a_i^{(T_{\text{prop}})}, \, 0, \, E_{\max} \right)
\]

donde:

- \(\lambda \in (0,1)\) es el factor de decaimiento (olvido). Típicamente \(\lambda = 0.9\).
- \(\gamma > 0\) es la tasa de ganancia por activación. Típicamente \(\gamma = 1.0\).
- \(E_{\max}\) es una cota superior para evitar crecimiento ilimitado. Por ejemplo, \(E_{\max} = 10\).
- \(a_i^{(T_{\text{prop}})}\) es la activación final del nodo \(i\) después de \(T_{\text{prop}}\) iteraciones.

**Nota sobre persistencia**: Solo la energía se persiste. Las fases \(\theta_i\) y las activaciones \(a_i\) se reinician en cada consulta.

**Interpretación**: La energía acumula la historia de activación del nodo. Nodos frecuentemente activados tendrán energía alta; nodos raramente usados verán decaer su energía lentamente. Esta energía podrá ser utilizada en futuras consultas, por ejemplo para sesgar la activación inicial o para podar nodos obsoletos (no implementado en MVP).

## 6. Extracción del contexto (Readout)

Después de la propagación y la actualización de energía, se determina la región final de contexto \(\mathcal{R}\) mediante un **umbral relativo** sobre las activaciones finales.

Sea \(a_{\max} = \max_{i \in R} a_i^{(T_{\text{prop}})}\) la activación máxima alcanzada. Definimos el umbral:

\[
\tau_{\text{rel}} = \tau \cdot a_{\max}
\]

donde \(\tau \in (0,1]\) es un parámetro de corte relativo (por ejemplo, \(\tau = 0.1\) o \(0.2\)).

El conjunto de nodos que forman el contexto es:

\[
\mathcal{R} = \{ i \in R \mid a_i^{(T_{\text{prop}})} > \tau_{\text{rel}} \}
\]

Los nodos en \(\mathcal{R}\) se devuelven ordenados por activación descendente, incluyendo sus metadatos, embeddings (si es necesario) y energía actual.

**Observación**: Este conjunto puede incluir nodos que no estaban en el conjunto candidato original \(C\), logrando así la expansión deseada.

## 7. Pseudocódigo de la etapa de propagación y memoria

```text
Entrada: C, S (matriz sobre C), grafo G, activaciones iniciales a_i(0) para i∈C, embeddings e_i, consulta e_q
Salida: contexto R_final, energías actualizadas

1. Construir R = C ∪ (vecinos de C)
2. Construir L según sección 3
3. Inicializar a_i(0) = exp(-||e_i - e_q||^2 / σ_q^2) para i∈C, 0 para i∈R\C
4. Para t = 0, 1, ..., T_prop-1:
       Para cada i∈R:
           suma = Σ_{j∈R} L_ij * a_j(t)
           grado_i = Σ_{j∈R} L_ij
           si grado_i > 0:
               a_i(t+1) = ReLU( (1-ε) * a_i(t) + ε * suma / grado_i )
           sino:
               a_i(t+1) = ReLU( (1-ε) * a_i(t) )
5. Para cada i∈R:
       E_i = clamp( λ * E_i + γ * a_i(T_prop), 0, E_max )
6. a_max = max_i a_i(T_prop)
   τ_rel = τ * a_max
   R_final = { i∈R | a_i(T_prop) > τ_rel }
7. Devolver R_final ordenado por a_i desc
```

## 8. Parámetros y valores sugeridos

| Parámetro | Símbolo | Valor sugerido | Observaciones |
|-----------|---------|----------------|---------------|
| Coeficiente de difusión | \(\varepsilon\) | 0.5 | Controla la mezcla entre autostate y vecinos. |
| Iteraciones de propagación | \(T_{\text{prop}}\) | 5 | Suficiente para alcanzar vecinos directos. |
| Función de activación | \(\phi\) | ReLU | Mantiene activaciones no negativas. |
| Factor de decaimiento de energía | \(\lambda\) | 0.9 | Olvido lento. |
| Ganancia de energía | \(\gamma\) | 1.0 | Refuerzo por activación. |
| Cota máxima de energía | \(E_{\max}\) | 10.0 | Evita crecimiento excesivo. |
| Umbral relativo de readout | \(\tau\) | 0.1 | Fracción del máximo de activación. |

---

Con esto se completa la definición matemática de la propagación y la memoria. La siguiente sección (Documento 4) integrará todas las etapas en un algoritmo completo de consulta con pseudocódigo ejecutable.
