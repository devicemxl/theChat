"""Constantes compartidas entre vistas.

Vive aparte de config.py para no mezclar valores de configuración de runtime
(get_secret) con constantes de UI.
"""

# Paleta curada de 8 colores para proyectos.
# Elegidos por buen contraste sobre fondo blanco y suficiente diferenciación
# entre sí para uso como marcadores visuales.
PROJECT_COLORS = [
    "#ef4444",  # rojo
    "#f59e0b",  # ámbar
    "#eab308",  # amarillo
    "#22c55e",  # verde
    "#06b6d4",  # cian
    "#3b82f6",  # azul
    "#8b5cf6",  # violeta
    "#ec4899",  # rosa
]
