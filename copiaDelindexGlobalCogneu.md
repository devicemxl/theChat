---
| key | value |
|--|--|
| tipo | índice maestro de la Enciclopedia CogNeu |
| documento | Índice General · Estructura por Partes y Capítulos |
| versión | 1.0 |
| estado | consolidado |
| fecha | 2026-05-03 |
| reemplaza | borrador de marzo 2026 + reformulación de abril 2026 + reconstrucción 0.5 de mayo 2026 |
| reemplazado_por | — |
| mantenedor | David |
---

# Índice Maestro · Enciclopedia CogNeu

## Arquitectura Cognitiva Gobernada para Sistemas Híbridos

---

## Propósito de este documento

Este índice define la estructura canónica de la Enciclopedia CogNeu. Establece nueve Partes temáticas, cuarenta y cuatro capítulos numerados consecutivamente y seis apéndices. Su función es triple: orientar la lectura por dependencias, fijar la numeración para referencias cruzadas internas, y declarar la secuencia argumental que cada Parte sostiene.

La numeración asignada en esta versión es estable. Los títulos de capítulos pueden refinarse durante la redacción; el ordinal asignado no.

---

## Estructura general

| Parte | Título | Rango | Foco |
|---|---|---|---|
| I | Visión y Compromiso | Cap. 1–3 | Manifiesto, arquitectura macro, plantillas formales |
| II | Fundamentos Conceptuales | Cap. 4–6 | Commit cognitivo, ontología, sinapsis tripartita |
| III | Fundamentos Axiomáticos | Cap. 7–10 | Teoría General de Sistemas Informacionales, neutrosofía no normalizada, ICM, incertidumbre |
| IV | Estados Cognitivos y Dinámica Discreta | Cap. 11–15 | MSC, transiciones, fenómeno límite, colapso |
| V | Acción y Geometría Cognitiva | Cap. 16–20 | Función de acción, ecuaciones de movimiento, geodésica |
| VI | Arquitectura del Sistema | Cap. 21–25 | Macro A, Macro B, Talents, simbólica ⊥₀, modularidad |
| VII | Componentes Operativos | Cap. 26–34 | NexusL, Runtime, VivaceGraph, gLEANN, ASP, trunKV, Bealach, nxDeck, Búsqueda Gobernada |
| VIII | Aplicaciones y Casos de Uso | Cap. 35–41 | Buscador, narrativas, reglas, noticias, código, lenguas, contabilidad |
| IX | Implementación y Hoja de Ruta | Cap. 42–44 | Mapa, roadmap, integraciones |
| Apéndices | A–F | — | Sistema axiomático reunido, glosarios, convenciones, isomorfismos, versionado, problemas abiertos |

---

## Niveles estructurales

```
PARTE (Volumen temático)
  └── CAPÍTULO (Monografía autocontenida)
        └── SECCIÓN (Ensayo técnico)
              └── Subsecciones
```

Invariantes en cada nivel:

1. Se declara explícitamente qué cubre y qué no cubre.
2. Se conecta hacia atrás (depende_de) y hacia adelante (habilita).
3. Se declara estado: versión, madurez, dependencias.

---

# PARTE I · Visión y Compromiso

*Por qué CogNeu existe, en qué se compromete, y cómo se navega esta enciclopedia.*

| Cap. | Título |
|---|---|
| 1 | Manifiesto: el sistema que sabe que no sabe |
| 2 | Arquitectura Macro: A, B, Talents, ⊥₀ |
| 3 | Niveles de la enciclopedia y plantillas formales |

**Hilo conductor:** del compromiso personal al método de organización del corpus.

---

# PARTE II · Fundamentos Conceptuales

*Las unidades atómicas de pensamiento del sistema.*

| Cap. | Título |
|---|---|
| 4 | Commit Cognitivo: el átomo del conocimiento |
| 5 | Ontología Interna del sistema |
| 6 | Sinapsis Tripartita Digitalizada |

**Hilo conductor:** del átomo al tejido — cómo las unidades discretas se organizan en una estructura regulada.

---

# PARTE III · Fundamentos Axiomáticos

*La teoría matemática que justifica la arquitectura.*

| Cap. | Título |
|---|---|
| 7 | Teoría General de Sistemas Informacionales con Curvatura Neutrosófica |
| 8 | Neutrosofía No Normalizada: T+I+F ≠ 1 como propiedad esencial |
| 9 | Invariante Cognitivo Multimodal (ICM) |
| 10 | Incertidumbre y Tensor I |

**Invariantes de Parte:**

1. Todo concepto formal se define antes de usarse.
2. Ninguna fórmula aparece sin interpretación conceptual.
3. Las analogías se marcan como controladas y se delimitan.
4. I nunca se trata como residuo de T y F.

---

# PARTE IV · Estados Cognitivos y Dinámica Discreta

*Cómo el sistema cambia de régimen.*

| Cap. | Título |
|---|---|
| 11 | Estados Cognitivos Base |
| 12 | Máquina de Estados Cognitivos (MSC) |
| 13 | Tabla Formal de Transiciones Entrópicas |
| 14 | Fenómeno Límite |
| 15 | Colapso y Ramificación |

**Hilo conductor:** del estado al régimen — cómo se distinguen estados cognitivos discretos y bajo qué condiciones la dinámica los cruza.

---

# PARTE V · Acción y Geometría Cognitiva

*La formulación variacional y geométrica del sistema.*

| Cap. | Título |
|---|---|
| 16 | Definición de Componentes Básicos |
| 17 | Función de Acción Cognitiva 𝒮[γ] |
| 18 | Ecuaciones de Movimiento Cognitivo |
| 19 | MSC como Sistema Dinámico |
| 20 | Ecuación Geodésica Cognitiva (EGC) |

**Hilo conductor:** del principio variacional a la geodésica — el sistema se desplaza minimizando 𝒮[γ] sobre un espacio curvado por I.

> **Nota arquitectónica:** En la reformulación de abril 2026, la antigua §5.8 que conectaba con la contabilidad fue retirada. Cap. 20 cierra Parte V en la EGC. La proyección al plano económico vive ahora íntegra en Cap. 41.

---

# PARTE VI · Arquitectura del Sistema

*Cómo se organiza el sistema en capas y macroprocesos.*

| Cap. | Título |
|---|---|
| 21 | Macro A — Ejecución y UX (Frontera, Control, Core) |
| 22 | Macro B — Computación por Contemplación |
| 23 | Talents y DSST: ciclo transversal en runtime |
| 24 | Simbólica Formal ⊥₀: contratos pre-runtime con Lean y Ada/SPARK |
| 25 | Arquitectura Modular de Cognición Especializada |

**Hilo conductor:** de la separación entre ejecución y contemplación a los mecanismos formales que garantizan que ambos macroprocesos preserven sus invariantes.

---

# PARTE VII · Componentes Operativos

*Las piezas concretas que ejecutan la arquitectura.*

| Cap. | Título |
|---|---|
| 26 | NexusL: lenguaje de descomposición y axiomas categoriales |
| 27 | NexusL Runtime: motor de ingestión en C puro |
| 28 | VivaceGraph: árbitro epistémico neutrosófico sobre graphlets |
| 29 | gLEANN: motor de búsqueda multidimensional HNSW |
| 30 | ASP / Clingo: motor de razonamiento simbólico formal |
| 31 | trunKV: persistencia versionada (canal Macro A↔B) |
| 32 | Bealach: validador formal Ada/SPARK |
| 33 | nxDeck y picoLM: capa de inferencia LLM local |
| 34 | Búsqueda Gobernada: MCTS Neutrosófico y Promotion Engine |

**Invariantes de Parte:**

1. Cada capítulo describe un componente con identidad propia: interfaz, contrato, estado interno, ciclo de vida.
2. Las dependencias entre componentes se declaran explícitamente y se diagraman.
3. La versión de cada componente sigue el patrón v0.x → v3.x establecido en CogNeu.

**Hilo conductor:** del lenguaje de tripletas a la búsqueda gobernada — cada componente es un eslabón en la cadena que convierte texto crudo en conocimiento epistémicamente evaluado.

### Justificación de Cap. 27 (NexusL Runtime)

Separado de Cap. 26 porque tiene identidad distinta. Cap. 26 desarrolla el lenguaje conceptual: tripletas, axiomas categoriales, semántica de composición. Cap. 27 desarrolla el motor: implementación en C puro, cuatro fases del pipeline (Descomposición Dirigida → Formación de Graphlets → Resolución de Entidades → Linealización a Tripletas), roadmap de siete hitos v1.1, integración con nxDeck para inferencia LLM local, constraints de hardware (ARM 4GB para componente standalone, laptop para CogNeu completo), y bifurcación de salida hacia los dos pipelines downstream (indexación y epistémico).

### Justificación de Cap. 34 (Búsqueda Gobernada)

MCTS aplicado al espacio de acciones de CogNeu, con value neutrosófico (T,I,F) provisto por Cap. 28 y verificación terminal en cascada (Cap. 30 → Cap. 32 → Cap. 24). El subproducto natural de la búsqueda — frecuencia de visita en trazas verificadas — constituye la señal de promoción del Promotion Engine: convierte la transición explícito→paramétrico en destilación gobernada por búsqueda en lugar de threshold estático. Posicionado en Parte VII como componente arquitectónico, no como aplicación. Refina la semántica operativa de (T, I, F) como value y conecta MSC con exploración vía componentes específicos del tensor I.

---

# PARTE VIII · Aplicaciones y Casos de Uso

*Tratados de aplicación con estatus epistemológico propio.*

| Cap. | Título |
|---|---|
| 35 | Buscador Semántico Local (RAG gobernado) |
| 36 | Interpretación de Documentos y Construcción de Narrativas |
| 37 | Generación de Reglas y Comprensión de Contextos |
| 38 | Evaluación Multidimensional de Noticias |
| 39 | Módulo Autogenerativo de Código |
| 40 | Estudio de Lenguas Muertas o en Peligro |
| 41 | Contabilidad de Costos para Desarrollo con LLM |

**Hilo conductor:** cada capítulo demuestra que el marco teórico y arquitectónico de Partes II–VII tiene consecuencias verificables en un dominio independiente. Las aplicaciones no ilustran la teoría: la validan al mostrar que produce instrumentos operativos genuinos.

> **Nota sobre Cap. 41 (Contabilidad):** este capítulo está en redacción activa siguiendo la metodología de un punto = un documento = un Q&A. Los archivos del proyecto que materializan su contenido — la serie 00 a 10 más 00B — son material de origen que se reescribe como tratado autocontenido bajo la estructura tres-actos: Acto I (problema y crítica de frameworks existentes), Acto II (corolario variacional, isomorfismo financiero), Acto III (instanciación operativa: jerarquía de identificadores, fases del ciclo, KPIs, Plan Maestro, auditoría, gobernanza semanal). La numeración interna existente (§32.9.x en archivos previos) se actualizará a §41.9.x al integrar.

---

# PARTE IX · Implementación y Hoja de Ruta

*El plan operativo del proyecto, distinto de su teoría.*

| Cap. | Título |
|---|---|
| 42 | Mapa de Implementación: estado de cada componente |
| 43 | Roadmap Técnico por fases |
| 44 | Integraciones Futuras |

**Hilo conductor:** del estado actual al horizonte abierto. No es teoría sobre el sistema sino plan sobre el proceso de construirlo.

---

# Apéndices

| Apéndice | Título |
|---|---|
| A | Sistema Axiomático Reunido (Axioma 0, ICM, Geodésica, Principio Variacional) |
| B | Glosario Neutrosófico |
| C | Convenciones de Notación |
| D | Tablas de Isomorfismos (Finanzas ↔ Cognición) |
| E | Convenciones de Versionado de Componentes (v0.x → v3.x) |
| F | Problemas Abiertos y Agenda de Investigación |

---

# Estado de redacción por capítulo

Esta tabla declara, para cada capítulo, qué material existe en el proyecto y qué trabajo de composición queda pendiente. Es la guía operativa para decidir el orden de redacción.

| Cap. | Estado | Material existente |
|---|---|---|
| 1 | A componer | `cogneu-vision.md` |
| 2 | A componer | `cogneu-00-macro.md` |
| 3 | A redactar | conversación marzo 2026 sobre niveles y plantillas |
| 4 | A componer | `01_commitCognitivo.md` |
| 5 | A componer | `02_ontologiaInterna.md` |
| 6 | A componer | `19_TripartiteSynapseDigitalizada.md` |
| 7 | A componer | `Teoría_General_de_Sistemas_Informacionales_-_Desarrollo_Completo.md` y partes III–V, VI–VIII |
| 8 | A redactar | extraído de Cap. 7; merece tratamiento independiente |
| 9 | A componer | `11_ICM.md` |
| 10 | A componer | `08_incertidumbre.md` |
| 11 | A componer | `03_estadosCognitivosBase1.md`, `04_estadosCognitivosBase2.md`, `05_estadosCognitivosBase3.md` |
| 12 | A componer | `06_maquinaEstadosCognitivosMSC.md` |
| 13 | A componer | `07_tablaFormalTransicionesEntropicas.md` |
| 14 | A componer | `09_fenomenoLimite.md` |
| 15 | A componer | `10_colapso.md` |
| 16 | A componer | `12_definicionComponentesBasicos.md` |
| 17 | A componer | `13_funcionAccionCognitiva.md` |
| 18 | A componer | `14_ecuacionesMovimientoCognitivo.md` |
| 19 | A componer | `15_MSCsistemaDinámico.md` |
| 20 | A componer | `16_ecuacionGeodesicaCognitiva.md` |
| 21 | A componer | `cogneu-01-core.md`, `cogneu-02-control.md`, `cogneu-03-frontera.md` |
| 22 | A componer | `cogneu-06-macro-b.md`, `cogneu-07/08/09/10-macro-b-z*`, `17_computationContemplation1.md` |
| 23 | A componer | `18_talents.md`, `cogneu-04-talents.md` |
| 24 | A componer | `cogneu-05-simbolico.md` |
| 25 | A componer | `Arquitectura_Modular_de_Cognición_Especializada` |
| 26 | A componer | `NexusL_Internal_Spec_v1_0.md` |
| 27 | A redactar | `NexusL_Runtime_Roadmap_v1_1.md`, `pipeline_completo_ingesta_DRS.md` |
| 28 | A componer | `VivaceGraph_CogNeu_Spec_v1_0.md` |
| 29 | A componer | `gLEANN_REPOSITIONED_MultiDimensional_SearchEngine.md`, `gLEANN_Component_Specification_v2_1_UPDATED.md`, `CHANGELOG_Spec_v2_0_to_v2_1.md` |
| 30 | A redactar | referencias dispersas en KB |
| 31 | A redactar | referencias dispersas en KB |
| 32 | A redactar | referencias dispersas en KB |
| 33 | A redactar | referencias en pipeline DRS y arquitectura macro |
| 34 | A redactar | discusión mayo 2026 |
| 35–40 | A redactar | propuestas conceptuales de marzo 2026 |
| 41 | En desarrollo activo | sesión actual en §41.9.7 (anteriormente §32.9.7); material origen: serie 00–10 más 00B |
| 42–44 | A redactar | originalmente Cap. 32–34 en la propuesta de marzo 2026 |

---

# Convenciones de la Enciclopedia

## Formato de capítulo

Cada capítulo lleva tabla de metadatos al inicio (tipo, parte, maturity, confidence, dependencias hacia atrás, lo que habilita hacia adelante), una sección explícita de alcance negativo (qué no cubre), cuerpo desarrollado con prosa rigurosa, derivaciones formales donde corresponda, y referencias bidireccionales al cierre.

## Estilo de redacción

- Prosa formal sin emojis en documentos técnicos.
- Derivaciones rigurosas con interpretación conceptual obligatoria.
- Sin truncación: la profundidad del tema es el único constraint.
- Cada sección verifica contra el índice formal antes de cierre.
- No se reciclan materiales previos sin evaluación independiente.

## Ciclo de redacción

Un punto del índice equivale a un documento equivale a un intercambio Q&A. Las introducciones de capítulo se escriben sólo después de que todos los puntos constituyentes estén completos. Las introducciones de Parte se escriben sólo después de que todos los capítulos de la Parte estén completos.

## Numeración

La numeración asignada en este documento es estable. Los títulos de capítulos pueden refinarse durante la redacción; el ordinal asignado no. Si un capítulo necesita partirse, los hijos heredan letras (Cap. 27a, 27b) en lugar de empujar la numeración global.

---

**Versión:** 1.0  
**Estado:** consolidado  
**Última actualización:** 2026-05-03  
**Mantenedor:** David
