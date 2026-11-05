# TripAdvisor Barcelona Scraper 🇪🇸🍽️

Extractor automatizado de alta fidelidad para obtener el **100% de los restaurantes de Barcelona** catalogados en TripAdvisor, desarrollado en **Python** con **Camoufox Anti-Detect** (motor Firefox parcheado a nivel C++ con huella realista TLS, HTTP/2 y Canvas) para eludir sistemas de protección contra bots y muros de consentimiento GDPR.

---

## 🎯 Datos Extraídos por Restaurante

El scraper captura tanto los datos primarios solicitados como metadatos de enriquecimiento y trazabilidad comercial:

| Campo | Descripción | Ejemplo |
| :--- | :--- | :--- |
| **Nombre** | Denominación comercial del restaurante | *Disfrutar* |
| **Dirección Completa** | Dirección unificada legible | *Carrer de Villarroel, 163, 08036 Barcelona, España* |
| **Calle** | Vía y número exacto | *Carrer de Villarroel, 163* |
| **Código Postal** | Código postal de Barcelona | *08036* |
| **Localidad** | Municipio o distrito | *Barcelona* |
| **Teléfono** | Número de contacto directo | *+34 933 48 68 96* |
| **Puntuación** | Calificación media (1.0 a 5.0) | *4.8* |
| **Total Opiniones** | Volumen de reseñas acumuladas | *2340* |
| **Tipo de Cocina** | Gastronomía / especialidad | *Mediterránea, Europea, Fusión* |
| **Rango de Precio** | Categoría económica | *€€€€* |
| **URL TripAdvisor** | Enlace canónico de la ficha | `https://www.tripadvisor.es/Restaurant_Review-g187497-...` |
| **Fecha Extracción** | Marca de tiempo UTC | *2026-11-05T19:30:00* |

---

## 🏗️ Arquitectura del Scraper

Para garantizar la cobertura del **100% de la ciudad** (~9.000 a 10.000 establecimientos) sin pérdida de progreso ante interrupciones de red, el sistema opera con arquitectura en dos fases respaldada por una base de datos local SQLite:

```
[ Paginación TripAdvisor Barcelona (g187497) ]
                  │
                  ▼ (Fase 1: --mode catalog)
       [ Indexador de URLs en SQLite ] ─── Registra IDs únicos (-d123456-)
                  │
                  ▼ (Fase 2: --mode detail)
     [ Extractor Profundo con Camoufox ] ─── Visita fichas pendientes
                  │
    ┌─────────────┴─────────────┐
    ▼                           ▼
[ Extracción LD+JSON ]    [ Fallbacks DOM ] ─── Captura teléfono y dirección
    └─────────────┬─────────────┘
                  ▼
      [ Actualización en SQLite ] ─── Checkpoint ACID automático
                  │
                  ▼ (Exportación)
   [ restaurantes_barcelona.csv ] ─── UTF-8 con BOM (Compatible con Excel)
```

1. **Fase 1 (Catalogación de URLs):** Recorre la paginación oficial (`oa0`, `oa30`, `oa60`, ...) e indexa todas las URLs de restaurantes de Barcelona en la base de datos `tripadvisor_barcelona.db`.
2. **Fase 2 (Extracción Profunda):** Procesa cada URL pendiente extrayendo el bloque estructurado `schema.org/Restaurant` (JSON-LD) y aplicando selectores de respaldo DOM si algún dato viene ofuscado.
3. **Persistencia ACID & Checkpointing:** Si el proceso se interrumpe (corte de luz, red o pausa manual), al relanzarlo **continúa exactamente donde quedó**, sin repetir restaurantes ya descargados.

---

## 🚀 Instalación Rápida

### En Windows (Doble Clic)

1. Ejecuta el archivo **`install.bat`** (crea el entorno virtual, instala dependencias y descarga el binario del navegador Camoufox).
2. Para iniciar el scraping, haz doble clic en **`run.bat`**.

### En Linux / macOS (Terminal)

```bash
# Dar permisos de ejecución
chmod +x install.sh run.sh

# Ejecutar el instalador
./install.sh

# Ejecutar el scraper
./run.sh
```

### Verificación Manual de Instalación

Puedes comprobar en cualquier momento que todos los módulos y binarios están operativos ejecutando:

```bash
python scraper.py --check-install
```

---

## 💻 Guía de Uso por Línea de Comandos

El script cuenta con una interfaz de consola completa (`CLI`) mediante argumentos:

### 1. Extracción Completa (Catálogo + Detalles)
Extrae todo el universo de restaurantes de Barcelona y genera el CSV:
```bash
python scraper.py --mode all
```

### 2. Solo Catalogar URLs (Fase 1)
Indexa las URLs en la base de datos local sin entrar a los detalles todavía:
```bash
python scraper.py --mode catalog
```
*Opcional: limitar a las primeras 10 páginas de prueba:*
```bash
python scraper.py --mode catalog --max-pages 10
```

### 3. Solo Extraer Detalles de Fichas Pendientes (Fase 2)
Procesa los restaurantes que ya están indexados en la base de datos:
```bash
python scraper.py --mode detail
```
*Opcional: procesar un lote de 100 restaurantes:*
```bash
python scraper.py --mode detail --limit 100
```

### 4. Exportar a CSV en Cualquier Momento
Genera o actualiza el archivo CSV a partir de la base de datos sin hacer peticiones de red:
```bash
python scraper.py --export-only --output mis_restaurantes.csv
```

### 5. Uso con Proxy Residencial / Rotativo
Si se requiere trabajar a gran escala mediante un proxy específico:
```bash
python scraper.py --proxy "http://usuario:contraseña@proxy-host:puerto"
```

### 6. Parámetros Avanzados

| Parámetro | Valor por defecto | Descripción |
| :--- | :--- | :--- |
| `--mode` | `all` | Modo: `all`, `catalog`, `detail` |
| `--start-page` | `1` | Página inicial del catálogo |
| `--max-pages` | `None` (todas) | Cantidad máxima de páginas a catalogar |
| `--limit` | `None` (todos) | Límite de fichas a procesar en modo detail |
| `--output` | `restaurantes_barcelona.csv` | Nombre del archivo CSV exportado |
| `--db` | `tripadvisor_barcelona.db` | Archivo de base de datos SQLite |
| `--proxy` | `None` | URL del servidor proxy |
| `--no-headless` | `False` | Muestra la ventana gráfica del navegador |
| `--delay-min` | `1.5` | Segundos mínimos de pausa aleatoria |
| `--delay-max` | `3.5` | Segundos máximos de pausa aleatoria |
| `--export-only` | `False` | Solo exporta el CSV desde la BD |
| `--check-install`| `False` | Ejecuta el autodiagnóstico del sistema |

---

## 🛡️ Evasión Anti-Bot y Estabilidad

- **Camoufox C++ Engine:** El navegador sustituye las firmas de automatización de Playwright/Selenium y genera huellas consistentes de WebGL, Canvas, fuentes y headers TLS propios de un usuario legítimo en Windows.
- **Manejo de Consentimiento GDPR:** Detecta e interactúa automáticamente con los cuadros de diálogo de consentimiento de cookies (OneTrust / Didomi) tanto en el DOM principal como en iframes aislados.
- **Delays con Jitter:** Introduce variaciones aleatorias entre peticiones para simular el comportamiento de navegación humana y prevenir bloqueos por ratio de peticiones.

---

## 📂 Estructura del Repositorio

```
tripadvisor-barcelona-scraper/
├── scraper.py                 # Núcleo del scraper con CLI y lógica Camoufox
├── requirements.txt           # Dependencias de Python (camoufox, playwright, bs4)
├── install.bat                # Instalador de 1 clic para Windows
├── run.bat                    # Lanzador para Windows
├── install.sh                 # Instalador de 1 clic para Linux/macOS
├── run.sh                     # Lanzador para Linux/macOS
├── .gitignore                 # Exclusiones de Git (base de datos, venv, caches)
└── README.md                  # Manual técnico y operativo de usuario
```

---

## 📄 Licencia

Este proyecto está bajo licencia MIT. Desarrollado con fines de investigación, análisis comercial e inteligencia de mercado.
