# TripAdvisor Multi-City Restaurant Scraper 🇪🇸🍽️

Extractor profesional de alta fidelidad para obtener el **100% de los restaurantes de cualquier ciudad** (Barcelona, Madrid, Valencia, Sevilla, Málaga, Bilbao, o cualquier municipio del mundo) catalogados en TripAdvisor. Desarrollado en **Python** con **Camoufox Anti-Detect** (motor Firefox parcheado a nivel C++ con huella realista TLS, HTTP/2 y Canvas) para eludir sistemas de protección contra bots y muros de consentimiento GDPR.

---

## 🎯 Datos Extraídos por Restaurante

El scraper captura tanto los datos primarios solicitados como metadatos de enriquecimiento y trazabilidad comercial:

| Campo | Descripción | Ejemplo |
| :--- | :--- | :--- |
| **Nombre** | Denominación comercial del restaurante | *Disfrutar* |
| **Dirección Completa** | Dirección unificada legible | *Carrer de Villarroel, 163, 08036 Barcelona, España* |
| **Calle** | Vía y número exacto | *Carrer de Villarroel, 163* |
| **Código Postal** | Código postal de la ciudad | *08036* |
| **Localidad** | Municipio o distrito | *Barcelona* |
| **Teléfono** | Número de contacto directo | *+34 933 48 68 96* |
| **Puntuación** | Calificación media (1.0 a 5.0) | *4.8* |
| **Total Opiniones** | Volumen de reseñas acumuladas | *2340* |
| **Tipo de Cocina** | Gastronomía / especialidad | *Mediterránea, Europea, Fusión* |
| **Rango de Precio** | Categoría económica | *€€€€* |
| **URL TripAdvisor** | Enlace canónico de la ficha | `https://www.tripadvisor.es/Restaurant_Review-...` |
| **Fecha Extracción** | Marca de tiempo UTC | *2026-11-05T19:30:00* |

---

## 🛡️ Análisis Técnico: Muros de Seguridad y Bloqueos de IP en TripAdvisor

TripAdvisor implementa uno de los perímetros de seguridad anti-bot más sofisticados de la web, administrado por **DataDome** (`geo.captcha-delivery.com`) junto a sistemas propios de limitación de tasa:

### 1. Vector de Detección por Huella de Navegador (Fingerprinting)
- **Firma TLS y JA4:** Las herramientas tradicionales de scraping (Requests, Scrapy, Puppeteer sin parches) utilizan stacks de red con firmas TLS (ClientHello, Cipher Suites, Extensiones) y configuraciones HTTP/2 que son identificadas inmediatamente como automatizadas en el primer paquete SYN/ACK.
- **Detección de WebDriver y APIs del DOM:** Playwright y Selenium dejan rastros en variables como `navigator.webdriver = true`, discrepancias en plugins, WebGL, Canvas y orden de evaluación de micro-tareas en el motor JS.
- **Solución implementada:** Se utiliza **Camoufox**, una bifurcación de Firefox con parches en el código fuente C++ que elimina `navigator.webdriver`, falsifica las huellas de Canvas/Audio/WebGL con entropía humana y emite cabeceras HTTP/2 y TLS idénticas a una instalación de Firefox legítima en Windows.

### 2. Muro de Consentimiento GDPR (OneTrust / Didomi)
- TripAdvisor no renderiza completamente los bloques de contacto ni permite interacción hasta que se acepta el consentimiento de cookies.
- Dichos cuadros suelen inyectarse dinámicamente o residir en **iframes aislados**.
- **Solución implementada:** La rutina `_handle_cookie_consent` inspecciona recursivamente `page.frames` buscando identificadores específicos (`#onetrust-accept-btn-handler`, `#didomi-notice-agree-button`) y resuelve el diálogo en milisegundos.

### 3. Rate Limiting Dinámico y Bloqueo de IPs
- DataDome no aplica una regla estática (ej. "máximo 100 peticiones por minuto"). En su lugar, calcula una **puntuación de anomalía en tiempo real** basada en:
  1. *Frecuencia y cadencia:* Ráfagas de peticiones continuas sin intervalos de lectura humana.
  2. *Patrón de navegación:* Cargar únicamente URLs sin interactuar con el scroll o el cursor.
  3. *Reputación de IP:* Puntuación del ASN (las IPs de datacenters como AWS, DigitalOcean, Hetzner son desafiadas con HTTP 403 casi al instante).

### 4. Por qué NO funcionan los Proxies Públicos Gratuitos
- Las listas públicas de proxies de internet (TheSpeedX, openproxylist, foros) contienen IPs que ya están en las listas negras globales de DataDome o son proxies transparentes que inyectan cabeceras `X-Forwarded-For` filtrando la IP real.
- Durante nuestras pruebas empíricas, el 100% de los proxies públicos gratuitos resultaron en `HTTP 403 Forbidden`, `SSL_ERROR_SYSCALL` o caídas inmediatas del handshake. Para scraping masivo continuo se requieren **proxies residenciales o móviles rotativos**.

---

## ⚙️ Arquitectura Técnica y Sistema Avanzado de Pacing Humano

Para mitigar los bloqueos de IP y permitir la extracción masiva de hasta 10.000 locales por ciudad, el scraper implementa una arquitectura desacoplada con protección adaptativa de IP:

```
[ Catálogo TripAdvisor de la Ciudad elegida ]
                     │
                     ▼ (Fase 1: --mode catalog)
       [ Indexador de URLs en SQLite ] ─── Registra IDs únicos (-d123456-)
                     │
                     ▼ (Fase 2: --mode detail)
     [ Extractor Profundo con Camoufox ] ─── Visita fichas pendientes
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  [ Sleep Jitter ]       [ Enfriamiento por Lotes ]
  (Pausa aleatoria        (Cada N peticiones: scroll
   entre locales)          suave y lectura humana)
        │                         │
        └────────────┬────────────┘
                     ▼
       ┌─────────────┴─────────────┐
       ▼                           ▼
[ Extracción LD+JSON ]     [ Fallbacks DOM ]
       └─────────────┬─────────────┘
                     ▼
         [ Checkpoint ACID SQLite ] ─── Estado guardado tras cada restaurante
                     │
                     ▼ (Exportación)
       [ restaurantes_<ciudad>.csv ] ─── UTF-8 con BOM (Excel)
```

### Mecanismos de Protección de IP Implementados

1. **Micro-Pausas con Jitter Aleatorio (`--delay-min` y `--delay-max`):**
   - Entre la apertura de una ficha y la siguiente se aplica un retardo flotante no determinista (por defecto de 2.0 a 4.5 segundos).
   - Evita la regularidad milimétrica que dispararía los algoritmos de detección de robots.
2. **Sleep de Transición de Catálogo (`--page-delay-min` y `--page-delay-max`):**
   - Pasar de una página de listado a la siguiente involucra mayor carga de red. Se aplica una pausa de 3.0 a 6.5 segundos para simular el tiempo que toma a un humano mirar la página antes de pulsar "Siguiente".
3. **Sleep Inteligente por Lotes de N Peticiones (`--batch-size` y `--batch-cooldown`):**
   - Tras procesar N peticiones (por defecto 15), el scraper no congela el proceso ciegamente con un `time.sleep()`.
   - Activa `_human_scroll_simulation`: ejecuta desplazamientos suaves (`window.scrollBy` con `behavior: 'smooth'`) hacia arriba y hacia abajo en la pantalla, realiza movimientos sutiles del ratón y pausas de 1.5 a 3.5 segundos entre desplazamientos, simulando una lectura atenta del menú o de las opiniones. Esto enfría la ventana de ráfaga del cortafuegos de DataDome.
4. **Detección Activa de Desafíos y Reintento Resiliente:**
   - La rutina `_detect_security_challenge` inspecciona el HTML buscando firmas de DataDome o respuestas 403.
   - Si se detecta un bloqueo temporal, activa un cooldown extendido con scroll activo o rota al siguiente proxy disponible si se configuró un archivo `--proxy-list`.
5. **Persistencia ACID & Checkpointing en SQLite:**
   - Si se interrumpe la sesión (corte de conexión, Ctrl+C o pausa manual), **no se pierde ningún dato**. Al relanzar el CLI, el sistema detecta los restaurantes ya procesados y continúa exactamente en el primer local pendiente.

---

## 💻 Manual de Uso del CLI al 100% (Casos de Uso Prácticos)

### Parámetros Disponibles

```text
Selección de Ciudad / Destino:
  --city CITY                   Nombre de la ciudad (ej: barcelona, madrid, valencia, sevilla...)
  --url URL                     URL directa de TripAdvisor (anula --city)
  --geo GEO                     Geo ID explícito (ej: g187497)
  --city-slug CITY_SLUG         Slug de la ciudad para la URL

Control de Flujo:
  --mode {all,catalog,detail}   Modo de ejecución (por defecto: all)
  --start-page START_PAGE       Página inicial para catalogar (por defecto: 1)
  --max-pages MAX_PAGES         Límite de páginas a catalogar
  --limit LIMIT                 Límite de restaurantes a procesar en modo detail

Almacenamiento y Salida:
  --output OUTPUT               Ruta del CSV de salida (por defecto: restaurantes_<ciudad>.csv)
  --db DB                       Ruta de la BD SQLite (por defecto: tripadvisor_<ciudad>.db)
  --export-only                 Exporta la BD a CSV sin hacer peticiones de red

Protección de IP y Simulación Humana:
  --delay-min DELAY_MIN         Segundos mínimos entre restaurantes (def: 2.0)
  --delay-max DELAY_MAX         Segundos máximos entre restaurantes (def: 4.5)
  --page-delay-min PAGE_MIN     Segundos mínimos entre páginas de catálogo (def: 3.0)
  --page-delay-max PAGE_MAX     Segundos máximos entre páginas de catálogo (def: 6.5)
  --batch-size BATCH_SIZE       Peticiones antes del enfriamiento inteligente (def: 15)
  --batch-cooldown-min C_MIN    Pausa mínima activa en enfriamiento de lote (def: 20.0)
  --batch-cooldown-max C_MAX    Pausa máxima activa en enfriamiento de lote (def: 40.0)

Red y Proxies:
  --proxy PROXY                 Proxy único (http://user:pass@host:port)
  --proxy-list PROXY_LIST       Archivo .txt con proxies para rotación automática
  --no-headless                 Abre la ventana gráfica del navegador
  --check-install               Diagnóstico de instalación
```

---

### Casos de Uso Comunes

#### Caso 1: Extracción completa de una ciudad predeterminada (Madrid)
Ejecuta la Fase 1 (catalogación completa de URLs) y la Fase 2 (extracción profunda) en secuencia:
```bash
python scraper.py --city madrid
```
*Genera:* `tripadvisor_madrid.db` y `restaurantes_madrid.csv`.

#### Caso 2: Extracción de cualquier ciudad o pueblo del mundo vía URL
Si una localidad no está en el diccionario precargado, copia el enlace directo desde el navegador:
```bash
python scraper.py --url "https://www.tripadvisor.es/Restaurants-g187514-Madrid.html"
# O un destino internacional:
python scraper.py --url "https://www.tripadvisor.es/Restaurants-g187147-Paris_Ile_de_France.html"
```

#### Caso 3: Prueba rápida de 5 páginas de catálogo y 30 fichas
Ideal para verificar la conexión y la calidad de los datos antes de un scraping masivo:
```bash
# 1. Catalogar 5 páginas (~150 restaurantes)
python scraper.py --city valencia --mode catalog --max-pages 5

# 2. Extraer los primeros 30 restaurantes
python scraper.py --city valencia --mode detail --limit 30
```

#### Caso 4: Máxima protección de IP sin proxies (Pacing ultra-humano)
Ajusta los retardos y acorta los lotes de peticiones para IPs residenciales fijas:
```bash
python scraper.py --city barcelona \
  --delay-min 3.0 \
  --delay-max 6.0 \
  --batch-size 10 \
  --batch-cooldown-min 30.0 \
  --batch-cooldown-max 50.0
```

#### Caso 5: Scraping con rotación de lista de proxies
Permite balancear las peticiones entre múltiples servidores proxy residenciales:
```bash
python scraper.py --city sevilla --proxy-list mis_proxies.txt
```
*(El archivo `mis_proxies.txt` debe contener una dirección por línea, ej: `http://user:pass@proxy1:8080`).*

#### Caso 6: Exportación instantánea a CSV sin tocar la red
Si el proceso se interrumpió y quieres obtener el CSV con todo lo acumulado hasta el momento:
```bash
python scraper.py --export-only --db tripadvisor_barcelona.db --output barcelona_actualizado.csv
```

---

## 🚀 Instalación y Despliegue Rápido

### En Windows (1 Clic)
1. Ejecuta **`install.bat`** (configura el entorno virtual, instala librerías y descarga el motor Camoufox).
2. Para lanzar el scraper, ejecuta **`run.bat`** o abre una terminal con el comando deseado.

### En Linux / macOS
```bash
chmod +x install.sh run.sh
./install.sh
./run.sh --city barcelona
```

### Verificación de Instalación
```bash
python scraper.py --check-install
```

---

## 📂 Estructura del Proyecto

```
tripadvisor-barcelona-scraper/
├── scraper.py                 # Motor principal multi-ciudad con Camoufox y SQLite
├── requirements.txt           # Dependencias oficiales (camoufox, playwright, beautifulsoup4)
├── install.bat                # Instalador desatendido para Windows
├── run.bat                    # Script lanzador para Windows
├── install.sh                 # Instalador desatendido para Linux/macOS
├── run.sh                     # Script lanzador para Linux/macOS
├── .gitignore                 # Exclusiones de Git (.db, .venv, caches)
└── README.md                  # Documentación técnica completa y manual de usuario
```

---

## 📄 Licencia y Autoría

- **Desarrollador:** Marlon Sarduy Machado ([UserZero075](https://github.com/UserZero075))
- **Licencia:** MIT License. Desarrollado con fines de análisis de datos e inteligencia de mercado.
