# Documento 4: Algoritmo completo de consulta y pseudocódigo

## 1. Preparación previa (precondiciones)

Antes de ejecutar consultas, se asume que se han completado las siguientes tareas de inicialización:

1. Se ha construido el índice HNSW con todos los embeddings de los nodos \(V\).
2. Se ha generado el grafo \(G=(V,E,w)\) a partir del HNSW (aristas no dirigidas con pesos basados en similitud).
3. Se han calculado las frecuencias naturales \(\omega_i\) para todos los nodos \(i \in V\).
4. Se ha inicializado la base SQLite con:
   - Tabla `nodes(id, embedding, metadata, energy)`.
   - Tabla `edges(src, dst, weight)`.
5. Los parámetros globales están fijados (valores sugeridos en documentos anteriores).

Estos datos no cambian durante una consulta, salvo la energía \(E_i\) de los nodos, que se actualiza en cada consulta.

---

## 2. Procedimiento principal

```
Procedimiento RKG_Consulta(e_q, parametros)
Entrada:
    e_q      : vector de embedding de la consulta (d dimensional)
    parametros: conjunto de parámetros globales (k_query, K, alfa, Δt,
                T_sync, epsilon, T_prop, lambda, gamma, E_max, tau, sigma_q)
Salida:
    contexto : lista ordenada de nodos activos (id, metadata, activación final, energía)

Inicio
    // Etapa 1: Búsqueda de candidatos mediante HNSW
    C ← HNSW_Buscar(e_q, k_query)

    // Etapa 2: Cargar datos de los candidatos y activación inicial
    Para cada i en C hacer
        e_i     ← obtener_embedding(i)        // desde SQLite o memoria
        omega_i ← obtener_frecuencia(i)       // precalculada
        E_i     ← obtener_energia(i)          // desde SQLite (persistente)
        a_i     ← exp( -||e_i - e_q||² / sigma_q² )
    FinPara

    // Etapa 3: Sincronización de fase (solo sobre C)
    theta ← Sincronizar(C, omega, w, K, alfa, Δt, T_sync)

    // Etapa 4: Construir matriz de sincronización S (sobre C)
    S ← ConstruirMatrizS(C, theta, w)

    // Etapa 5: Construir subgrafo de expansión R = C ∪ vecinos(C)
    R ← C
    Para cada i en C hacer
        Para cada j en Vecinos(i) hacer
            Si j no está en R entonces
                R ← R ∪ {j}
            FinSi
        FinPara
    FinPara

    // Etapa 6: Inicializar activaciones para nodos en R \ C a cero
    Para cada i en R \ C hacer
        a_i ← 0
    FinPara

    // Etapa 7: Construir matriz de conductancia L sobre R
    L ← ConstruirMatrizL(R, C, S, w)

    // Etapa 8: Propagación de activación normalizada
    a ← PropagarActivacion(R, C, L, a, epsilon, T_prop)

    // Etapa 9: Actualización de energía persistente
    Para cada i en R hacer
        E_i ← clamp( lambda * E_i + gamma * a_i, 0, E_max )
        ActualizarEnergiaEnSQLite(i, E_i)
    FinPara
    ConfirmarTransaccion()

    // Etapa 10: Extracción de contexto (readout)
    a_max ← max_{i en R} a_i
    tau_rel ← tau * a_max
    contexto ← vacio

    Para cada i en R hacer
        Si a_i > tau_rel entonces
            contexto ← contexto ∪ {(i, metadata_i, a_i, E_i)}
        FinSi
    FinPara

    Ordenar contexto por a_i descendente

    Retornar contexto
Fin
```

---

## 3. Subprocedimiento de sincronización

```
Procedimiento Sincronizar(C, omega, w, K, alfa, Δt, T_sync)
Entrada:
    C      : conjunto de nodos candidatos
    omega  : vector de frecuencias naturales ω_i para i ∈ C
    w      : matriz de pesos de aristas w_ij para (i,j) ∈ E_C
    K, alfa, Δt, T_sync : parámetros de sincronización
Salida:
    theta  : fases finales θ_i para i ∈ C

Inicio
    // Inicializar fases a cero
    Para cada i en C hacer
        theta_i ← 0
    FinPara

    Para t = 1 hasta T_sync hacer
        // Calcular incrementos δ_i
        Para cada i en C hacer
            suma ← 0
            num_vecinos ← 0
            Para cada j en Vecinos_C(i) hacer   // vecinos de i que están en C
                Δomega ← omega_i - omega_j
                acoplamiento ← K * w_ij * exp(-alfa * Δomega²)
                suma ← suma + acoplamiento * sin(theta_j - theta_i)
                num_vecinos ← num_vecinos + 1
            FinPara

            Si num_vecinos > 0 entonces
                delta_i ← suma / num_vecinos
            Sino
                delta_i ← 0
            FinSi
        FinPara

        // Actualizar fases (Euler explícito síncrono)
        Para cada i en C hacer
            theta_i ← theta_i + Δt * (omega_i + delta_i)
        FinPara
    FinPara

    Retornar theta
Fin
```

---

## 4. Subprocedimiento de construcción de la matriz de sincronización \(S\)

```
Procedimiento ConstruirMatrizS(C, theta, w)
Entrada:
    C     : conjunto de nodos candidatos
    theta : fases finales θ_i para i ∈ C
    w     : pesos w_ij para aristas en E_C
Salida:
    S     : matriz de coherencia de tamaño |C| × |C| (dispersa)

Inicio
    Para cada i en C hacer
        Para cada j en C, j ≠ i hacer
            Si (i,j) ∈ E_C entonces   // existe arista entre i y j en el subgrafo C
                S[i,j] ← w_ij * (1 + cos(theta_i - theta_j)) / 2
            Sino
                S[i,j] ← 0
            FinSi
        FinPara
    FinPara

    Retornar S
Fin
```

---

## 5. Subprocedimiento de construcción de la matriz de conductancia \(L\)

```
Procedimiento ConstruirMatrizL(R, C, S, w)
Entrada:
    R  : conjunto de nodos en el subgrafo de expansión
    C  : conjunto de candidatos (C ⊆ R)
    S  : matriz de sincronización sobre C
    w  : pesos de aristas del grafo completo G
Salida:
    L  : matriz de conductancia de tamaño |R| × |R|

Inicio
    Para cada i en R hacer
        Para cada j en R, j ≠ i hacer
            Si i ∈ C y j ∈ C entonces
                // Ambos son candidatos: usar coherencia de sincronización
                L[i,j] ← S[i,j]
            Sino Si (i ∈ C y j ∉ C) o (i ∉ C y j ∈ C) entonces
                // Un extremo es candidato y el otro es vecino externo
                Si (i,j) ∈ E entonces
                    L[i,j] ← w_ij
                Sino
                    L[i,j] ← 0
                FinSi
            Sino
                // Ambos son externos: no propagar (por ahora)
                L[i,j] ← 0
            FinSi
        FinPara
    FinPara

    Retornar L
Fin
```

---

## 6. Subprocedimiento de propagación de activación

```
Procedimiento PropagarActivacion(R, C, L, a_inicial, epsilon, T_prop)
Entrada:
    R        : conjunto de nodos en el subgrafo de expansión
    C        : conjunto de candidatos
    L        : matriz de conductancia sobre R
    a_inicial: vector de activaciones iniciales a_i(0)
               (para i ∈ C: según similitud; para i ∈ R\C: 0)
    epsilon  : coeficiente de difusión (0 < epsilon < 1)
    T_prop   : número de iteraciones de propagación
Salida:
    a        : vector de activaciones finales a_i(T_prop)

Inicio
    // Copiar activaciones iniciales a la variable de trabajo
    a ← a_inicial

    Para t = 0 hasta T_prop - 1 hacer
        a_nuevo ← vector vacío

        Para cada i en R hacer
            suma ← 0
            grado ← 0

            Para cada j en R hacer
                Si L[i,j] > 0 entonces
                    suma ← suma + L[i,j] * a[j]
                    grado ← grado + L[i,j]
                FinSi
            FinPara

            Si grado > 0 entonces
                valor ← (1 - epsilon) * a[i] + epsilon * (suma / grado)
            Sino
                valor ← (1 - epsilon) * a[i]
            FinSi

            a_nuevo[i] ← Max(0, valor)   // ReLU
        FinPara

        a ← a_nuevo
    FinPara

    Retornar a
Fin
```

---

## 7. Notas sobre la implementación

### 7.1 Complejidad computacional

| Etapa | Complejidad típica |
|-------|--------------------|
| Búsqueda HNSW | \(O(\log N)\) promedio |
| Carga de candidatos | \(O(k_{\text{query}})\) |
| Sincronización | \(O(T_{\text{sync}} \cdot |E_C|)\) |
| Construcción de \(S\) | \(O(|E_C|)\) |
| Construcción de \(R\) | \(O(k_{\text{query}} \cdot d_{\text{avg}})\) |
| Propagación | \(O(T_{\text{prop}} \cdot |E_R|)\) |
| Actualización de energía | \(O(|R|)\) |
| Readout | \(O(|R| \log |R|)\) |

Donde:
- \(k_{\text{query}} = |C|\).
- \(d_{\text{avg}}\) es el grado medio del grafo \(G\).
- \(|E_C| \le k_{\text{query}}^2 / 2\) en el peor caso denso.
- \(|E_R| \approx |C| \cdot d_{\text{avg}} + d_{\text{avg}}\).

Con valores típicos (\(k_{\text{query}} = 50\), \(d_{\text{avg}} = 16\)), el coste es insignificante en CPU.

### 7.2 Transacciones y consistencia

La actualización de energía debe ejecutarse dentro de una transacción SQLite para garantizar la integridad de los datos si varias consultas se procesan de manera concurrente. En una implementación con un único hilo de escritura, bastará con agrupar todos los `UPDATE` y ejecutar `COMMIT` al final.

### 7.3 Reutilización de estructuras

Para acelerar las consultas repetidas, se recomienda precalcular y cachear en memoria:

- La matriz \(w\) de pesos de aristas.
- Las frecuencias \(\omega_i\).
- La estructura de vecindades \(\mathcal{N}_i\).

Solo se leen de SQLite los embeddings y la energía al inicio de la consulta; la energía actualizada se escribe al final.

---

## 8. Resumen del flujo completo

```
Consulta (e_q)
      │
      ▼
HNSW buscar candidatos C (top k_query)
      │
      ▼
Cargar datos (embeddings, frecuencias, energía)
      │
      ▼
Inicializar activaciones a_i(0) para i ∈ C
      │
      ▼
Sincronización de fase sobre C (Kuramoto local)
      │
      ▼
Construir matriz S sobre C
      │
      ▼
Expandir R = C ∪ vecinos(C)
      │
      ▼
Construir matriz de conductancia L
      │
      ▼
Propagar activación durante T_prop iteraciones
      │
      ▼
Actualizar energía persistente E_i
      │
      ▼
Extraer contexto: nodos con a_i > τ * max(a)
      │
      ▼
Devolver contexto ordenado
```

---

Con esto se cierra la serie de documentos matemáticos. El sistema queda completamente especificado desde la notación hasta el pseudocódigo ejecutable.