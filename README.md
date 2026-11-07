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

## 🔀 Tres Motores Disponibles: `scraper.py`, `scraper_ipw.py` y `scraper_fast.py`

El proyecto incluye tres implementaciones complementarias con la misma capa de datos (SQLite + exportación CSV, esquema idéntico de 12 columnas), permitiendo elegir el mejor balance entre evasión de huella y velocidad:

| Característica | `scraper.py` (Camoufox) | `scraper_ipw.py` (Playwright) | `scraper_fast.py` (Híbrido Ultra-Rápido) |
| :--- | :--- | :--- | :--- |
| **Motor** | Camoufox (Firefox parcheado, perfil persistente) | invisible_playwright (Firefox C++, perfil efímero) | invisible_playwright (sesión) + `curl_cffi` (HTTP nativo) |
| **Entrada / Telemetría** | Scroll y pausas humanas | Scroll, pausas y **cursor humanizado** | Telemetría real en handshake + peticiones HTTP directas |
| **Firma TLS / HTTP2** | Firefox real | Firefox real | TLS impersonation nativa `firefox133` |
| **Velocidad de Fichas** | ~6-8 fichas/min | ~6-10 fichas/min (o ~16-20 con multi-worker) | **~25-35 fichas/min sostenidas (pico ~100)** |
| **Consumo CPU / RAM** | Moderado (1 proceso navegador) | Alto por worker en headless | Mínimo (<1% CPU, ~50 MB RAM) |
| **Ideal para** | Pruebas estándar con IP limpia | Evasión profunda cuando hay bloqueo estricto | **Extracciones masivas (5.000 - 10.000 fichas en <1 hora)** |

### Motor Híbrido Ultra-Rápido (`scraper_fast.py`)

Resuelve el cuello de botella del rendering en navegador:
1. Abre `invisible_playwright` durante 2 segundos una sola vez al inicio para resolver el handshake de DataDome y extraer una cookie válida (`datadome`) y las cabeceras exactas de Firefox.
2. Descarga el HTML crudo de cada ficha vía `curl_cffi` con impersonación de TLS `firefox133` en ~300-500ms por petición.
3. Extrae el bloque estructurado Schema.org (`application/ld+json`) directamente en memoria con expresiones regulares y JSON parsing, obteniendo teléfono, dirección completa, puntuación, cocina y precio sin ejecutar JavaScript en cada ficha.
4. Si DataDome renueva el desafío (403), vuelve a llamar al navegador en segundo plano de forma transparente y reanuda el lote sin interrupciones.

#### Uso de `scraper_fast.py`:
```bash
# Extraer 5000 fichas a ritmo seguro (~25-35 fichas/minuto):
./run_barcelona_fast.sh
# O directamente:
xvfb-run -a python scraper_fast.py --city barcelona --mode detail --limit 5000 --geo-filter g187497 --delay 0.45
```

### ⚖️ Análisis de Protección de IP: Por qué se calibró el ritmo de ~100 a ~25-35 fichas/minuto

Durante las pruebas de estrés empíricas con `scraper_fast.py` se demostró que el motor es técnicamente capaz de alcanzar **~100 fichas por minuto** con 0 bloqueos iniciales. Sin embargo, para extracciones masivas completas (>5.000 locales) se calibró el ritmo operativo sostenido a **~25-35 fichas por minuto** por estrictas razones de supervivencia de la dirección IP pública:

#### 1. Detección de Huella vs. Limitación Volumétrica (Rate-Limiting)
DataDome no solo opera evaluando la coherencia criptográfica de TLS y la telemetría del navegador; en sus nodos de borde (CloudFront / Envoy) ejecuta un **algoritmo de cubo de tokens (Token Bucket / Leaky Bucket)** asignado a cada IP pública.
- La **huella** (cifrado TLS de Firefox, cabeceras HTTP/2, cookies firmadas) permite pasar el primer filtro y entrar sin captcha.
- El **volumen**, no obstante, cuenta el número acumulado de peticiones por ventana de tiempo (`requests/window`).

#### 2. El disparador de la cabecera `x-dd-b: 2`
Al sostener un caudal de ~100 peticiones por minuto durante más de 10-12 minutos consecutivos (~1.000 a 1.200 fichas seguidas desde una única IP pública sin proxies rotativos residenciales):
- El modelo estadístico de DataDome infiere automáticamente comportamiento no humano por densidad de tráfico atípica, inyectando la cabecera de control `x-dd-b: 2` (indicador de inspección reforzada).
- Activa un desafío `interstitial` / `Device Check` (`geo.captcha-delivery.com`) que exige al cliente demostrar de nuevo actividad humana en navegador real.
- Si un scraper ignora este aviso y continúa martillando a 100 req/min, DataDome escala de un *soft rate-limit* temporal a un **bloqueo estricto de IP (Hard Ban)** en su red global de reputación.

#### 3. El balance óptimo implementado en producción (~25 - 35 fichas/min)
Para blindar la IP y permitir completar los **5.931 restaurantes reales sin interrupciones ni bloqueos**, se implementó la siguiente estrategia:
1. **Pacing base seguro:** Intervalo entre peticiones de `0.45s - 0.55s` con fluctuación aleatoria (jitter).
2. **Ventanas de drenaje del bucket (Cooldowns periódicos):** Cada 40 fichas descargadas, el script suspende las peticiones durante 8 a 14 segundos, permitiendo que el contador del *leaky bucket* de DataDome se vacíe por debajo del umbral de alarma.
3. **Manejador reactivo de Device Check:** Si DataDome solicita una reevaluación (`status 403` o interstitial), `FastSession.refresh_session()` invoca `invisible_playwright` en un display virtual Xvfb, espera a que el tag JS resuelva la comprobación de dispositivo con micro-movimientos de scroll y adquiere una nueva cookie legítima sin intervención manual.

**Resultado obtenido:** Se procesaron 5.931 fichas reales en 2.9 horas continuas, con 0 baneos de IP y una tasa de teléfonos capturados del 95.0%.

### Instalación del motor alternativo

```bash
uv venv --python 3.11 .venv-ipw
VIRTUAL_ENV=.venv-ipw uv pip install -r requirements-ipw.txt
.venv-ipw/bin/invisible-playwright fetch      # descarga el motor (~260 MB)
chmod +x run_ipw.sh
```

En distribuciones con `libstdc++` antiguo (Ubuntu 20.04, Debian 10) el motor necesita una biblioteca más reciente; `run_ipw.sh` ya exporta `LD_LIBRARY_PATH` apuntando a `~/conda-gcc/lib` si existe.

### Uso

```bash
./run_ipw.sh --city barcelona --mode catalog --max-pages 20     # cataloga ~600 fichas
./run_ipw.sh --city barcelona --mode detail --limit 500         # extrae 500 fichas
./run_ipw.sh --city barcelona                                   # ambas fases
./run_ipw.sh --export-only --db tripadvisor_barcelona_ipw.db --output barcelona.csv
```

Ambos motores aceptan los mismos parámetros de pacing (`--delay-min`, `--delay-max`, `--page-delay-min`, `--page-delay-max`, `--batch-size`, `--batch-cooldown-min`, `--batch-cooldown-max`) y comparten la base de datos si se les apunta al mismo fichero, por lo que se puede empezar con uno y continuar con el otro sin perder progreso.

### Notas de implementación del motor alternativo

- **Validación de identidad de ficha:** antes de guardar, se comprueba que el `d{ID}` de la URL original aparezca en la URL final. Si TripAdvisor sirve otra ficha (redirección o ficha retirada), el registro se descarta en lugar de guardar datos ajenos.
- **Selección del bloque de datos correcto:** una ficha inyecta varios bloques `application/ld+json` (restaurante + productos turísticos patrocinados). El parser puntúa cada bloque por presencia de dirección, teléfono, valoración, cocina y rango de precio y elige el de mayor puntuación, evitando que un tour patrocinado contamine el registro.
- **Normalización de tipos:** los campos de `ld+json` pueden llegar como cadena, número, lista u objeto anidado (por ejemplo `addressCountry`); se normalizan antes de escribir en SQLite para no romper la exportación.
- **Resiliencia:** cada ficha fallida se deja en estado `pending` y se reintenta en la siguiente ejecución; el CSV solo incluye registros `done`.

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
tripadvisor-restaurant-scraper/
├── scraper.py                 # Motor principal multi-ciudad con Camoufox y SQLite
├── scraper_ipw.py             # Motor alternativo con invisible_playwright (Firefox C++)
├── scraper_fast.py            # Motor híbrido ultra-rápido (curl_cffi + TLS impersonation)
├── run_barcelona_fast.sh      # Runner automatizado con pacing adaptativo (~30 fichas/min)
├── run_ipw.sh                 # Script lanzador del motor invisible_playwright
├── requirements.txt           # Dependencias del motor Camoufox
├── requirements-ipw.txt       # Dependencias de invisible_playwright y curl_cffi
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
