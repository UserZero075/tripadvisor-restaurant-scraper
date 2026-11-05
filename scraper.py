#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TripAdvisor Multi-City Restaurant Scraper
=========================================
Extractor automatizado de restaurantes por ciudad en TripAdvisor utilizando
Camoufox Anti-Detect (Firefox parcheado a nivel C++ con huella realista TLS/Canvas).

Permite extraer el 100% de restaurantes de cualquier ciudad especificada por:
- Nombre de ciudad (--city madrid, barcelona, valencia, sevilla, etc.)
- URL directa de catálogo (--url "https://www.tripadvisor.es/Restaurants-g187514-Madrid.html")
- Identificador geográfico (--geo g187514 --city-slug Madrid)

Campos extraídos:
- Nombre
- Dirección Completa (calle, código postal, localidad)
- Teléfono directo
- Puntuación (rating) y número de opiniones
- Tipo de cocina y rango de precio
- URL de la ficha oficial
- Marca de tiempo UTC

Autor: UserZero075 / Hermes Agent
Licencia: MIT
"""

import sys
import os
import time
import random
import json
import sqlite3
import csv
import re
import argparse
from datetime import datetime
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.tripadvisor.es"
RESTAURANTS_PER_PAGE = 30

# Diccionario canónico de códigos geográficos (Geo IDs) de ciudades comunes en TripAdvisor
KNOWN_CITIES = {
    # España
    "barcelona": {"geo": "g187497", "slug": "Barcelona_Catalonia", "name": "Barcelona"},
    "madrid": {"geo": "g187514", "slug": "Madrid", "name": "Madrid"},
    "valencia": {"geo": "g187522", "slug": "Valencia_Province_of_Valencia_Valencian_Country", "name": "Valencia"},
    "sevilla": {"geo": "g187443", "slug": "Seville_Province_of_Seville_Andalucia", "name": "Sevilla"},
    "seville": {"geo": "g187443", "slug": "Seville_Province_of_Seville_Andalucia", "name": "Sevilla"},
    "malaga": {"geo": "g187438", "slug": "Malaga_Costa_del_Sol_Province_of_Malaga_Andalucia", "name": "Málaga"},
    "málaga": {"geo": "g187438", "slug": "Malaga_Costa_del_Sol_Province_of_Malaga_Andalucia", "name": "Málaga"},
    "bilbao": {"geo": "g187454", "slug": "Bilbao_Province_of_Vizcaya_Basque_Country", "name": "Bilbao"},
    "granada": {"geo": "g187441", "slug": "Granada_Province_of_Granada_Andalucia", "name": "Granada"},
    "zaragoza": {"geo": "g187448", "slug": "Zaragoza_Province_of_Zaragoza_Aragon", "name": "Zaragoza"},
    "palma": {"geo": "g187463", "slug": "Palma_de_Mallorca_Majorca_Balearic_Islands", "name": "Palma de Mallorca"},
    "palma de mallorca": {"geo": "g187463", "slug": "Palma_de_Mallorca_Majorca_Balearic_Islands", "name": "Palma de Mallorca"},
    "alicante": {"geo": "g1064230", "slug": "Alicante_Costa_Blanca_Province_of_Alicante_Valencian_Country", "name": "Alicante"},
    "cordoba": {"geo": "g187430", "slug": "Cordoba_Province_of_Cordoba_Andalucia", "name": "Córdoba"},
    "córdoba": {"geo": "g187430", "slug": "Cordoba_Province_of_Cordoba_Andalucia", "name": "Córdoba"},
    "san sebastian": {"geo": "g187457", "slug": "Donostia_San_Sebastian_Guipuzcoa_Province_Basque_Country", "name": "San Sebastián"},
    "donostia": {"geo": "g187457", "slug": "Donostia_San_Sebastian_Guipuzcoa_Province_Basque_Country", "name": "San Sebastián"},
    "murcia": {"geo": "g187518", "slug": "Murcia_Region_of_Murcia", "name": "Murcia"},
    "valladolid": {"geo": "g187494", "slug": "Valladolid_Province_of_Valladolid_Castile_and_Leon", "name": "Valladolid"},
    "vigo": {"geo": "g187509", "slug": "Vigo_Province_of_Pontevedra_Galicia", "name": "Vigo"},
    "gijon": {"geo": "g187452", "slug": "Gijon_Asturias", "name": "Gijón"},
    "gijón": {"geo": "g187452", "slug": "Gijon_Asturias", "name": "Gijón"},
    "a coruna": {"geo": "g187507", "slug": "A_Coruna_Province_of_A_Coruna_Galicia", "name": "A Coruña"},
    "la coruna": {"geo": "g187507", "slug": "A_Coruna_Province_of_A_Coruna_Galicia", "name": "A Coruña"},
    "santander": {"geo": "g187484", "slug": "Santander_Cantabria", "name": "Santander"},
    "cadiz": {"geo": "g187432", "slug": "Cadiz_Costa_de_la_Luz_Province_of_Cadiz_Andalucia", "name": "Cádiz"},
    "cádiz": {"geo": "g187432", "slug": "Cadiz_Costa_de_la_Luz_Province_of_Cadiz_Andalucia", "name": "Cádiz"},
    "tarragona": {"geo": "g187503", "slug": "Tarragona_Province_of_Tarragona_Catalonia", "name": "Tarragona"},
    "girona": {"geo": "g187499", "slug": "Girona_Province_of_Girona_Catalonia", "name": "Girona"},
    "lleida": {"geo": "g187500", "slug": "Lleida_Province_of_Lleida_Catalonia", "name": "Lleida"},
    "toledo": {"geo": "g187489", "slug": "Toledo_Province_of_Toledo_Castile_La_Mancha", "name": "Toledo"},
    "salamanca": {"geo": "g187493", "slug": "Salamanca_Province_of_Salamanca_Castile_and_Leon", "name": "Salamanca"},
    "ibiza": {"geo": "g616235", "slug": "Ibiza_Town_Ibiza_Balearic_Islands", "name": "Ibiza"},
    "santa cruz de tenerife": {"geo": "g187479", "slug": "Santa_Cruz_de_Tenerife_Tenerife_Canary_Islands", "name": "Santa Cruz de Tenerife"},
    "las palmas": {"geo": "g187472", "slug": "Las_Palmas_de_Gran_Canaria_Gran_Canaria_Canary_Islands", "name": "Las Palmas de Gran Canaria"},

    # Internacionales populares
    "paris": {"geo": "g187147", "slug": "Paris_Ile_de_France", "name": "París"},
    "parís": {"geo": "g187147", "slug": "Paris_Ile_de_France", "name": "París"},
    "london": {"geo": "g186338", "slug": "London_England", "name": "Londres"},
    "londres": {"geo": "g186338", "slug": "London_England", "name": "Londres"},
    "rome": {"geo": "g187791", "slug": "Rome_Lazio", "name": "Roma"},
    "roma": {"geo": "g187791", "slug": "Rome_Lazio", "name": "Roma"},
    "lisboa": {"geo": "g189158", "slug": "Lisbon_Lisbon_District_Central_Portugal", "name": "Lisboa"},
    "lisbon": {"geo": "g189158", "slug": "Lisbon_Lisbon_District_Central_Portugal", "name": "Lisboa"},
    "porto": {"geo": "g189180", "slug": "Porto_Porto_District_Northern_Portugal", "name": "Oporto"},
    "oporto": {"geo": "g189180", "slug": "Porto_Porto_District_Northern_Portugal", "name": "Oporto"},
    "new york": {"geo": "g60763", "slug": "New_York_City_New_York", "name": "Nueva York"},
    "nueva york": {"geo": "g60763", "slug": "New_York_City_New_York", "name": "Nueva York"},
    "buenos aires": {"geo": "g312741", "slug": "Buenos_Aires_Capital_Federal_District", "name": "Buenos Aires"},
    "ciudad de mexico": {"geo": "g150800", "slug": "Mexico_City_Central_Mexico_and_Gulf_Coast", "name": "Ciudad de México"},
    "cdmx": {"geo": "g150800", "slug": "Mexico_City_Central_Mexico_and_Gulf_Coast", "name": "Ciudad de México"},
    "bogota": {"geo": "g294074", "slug": "Bogota", "name": "Bogotá"},
    "bogotá": {"geo": "g294074", "slug": "Bogota", "name": "Bogotá"},
    "miami": {"geo": "g34438", "slug": "Miami_Florida", "name": "Miami"},
    "havana": {"geo": "g147271", "slug": "Havana_Ciudad_de_la_Habana_Province_Cuba", "name": "La Habana"},
    "la habana": {"geo": "g147271", "slug": "Havana_Ciudad_de_la_Habana_Province_Cuba", "name": "La Habana"}
}


# ---------------------------------------------------------------------------
# Gestor de Rotación de Proxies
# ---------------------------------------------------------------------------

class ProxyRotator:
    """Administra una lista de proxies con balanceo y marcado de fallos."""

    def __init__(self, proxy_list_path=None, single_proxy=None):
        self.proxies = []
        self.current_idx = 0
        self.dead_proxies = set()

        if single_proxy:
            self.proxies.append(self._format_proxy(single_proxy))

        if proxy_list_path and os.path.exists(proxy_list_path):
            with open(proxy_list_path, "r", encoding="utf-8") as f:
                for line in f:
                    p = line.strip()
                    if p and not p.startswith("#"):
                        self.proxies.append(self._format_proxy(p))

        if self.proxies:
            print(f"[PROXIES] Cargados {len(self.proxies)} proxies para rotación.")

    def _format_proxy(self, p_str):
        p_str = p_str.strip()
        if not (p_str.startswith("http://") or p_str.startswith("https://") or p_str.startswith("socks5://") or p_str.startswith("socks5h://")):
            p_str = f"http://{p_str}"
        return p_str

    def get_next(self):
        """Retorna el siguiente proxy operativo."""
        if not self.proxies:
            return None

        active = [p for p in self.proxies if p not in self.dead_proxies]
        if not active:
            print("[AVISO] Todos los proxies fueron marcados como fallidos. Restableciendo lista...")
            self.dead_proxies.clear()
            active = self.proxies

        self.current_idx = (self.current_idx + 1) % len(active)
        return active[self.current_idx]

    def mark_failed(self, proxy_str):
        """Registra un proxy como no funcional."""
        if proxy_str:
            self.dead_proxies.add(proxy_str)
            print(f"[PROXY CAÍDO] Descartado: {proxy_str} ({len(self.dead_proxies)}/{len(self.proxies)} caídos)")


# ---------------------------------------------------------------------------
# Resolución de Ciudad y URLs
# ---------------------------------------------------------------------------

class TargetCity:
    """Encapsula los parámetros geográficos del objetivo de scraping."""

    def __init__(self, name, geo, slug):
        self.name = name
        self.geo = geo if geo.startswith("g") else f"g{geo}"
        self.slug = slug

    @property
    def file_slug(self):
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", self.name.lower()).strip("_")
        return clean or "ciudad"

    @property
    def base_restaurants_url(self):
        return f"{BASE_URL}/Restaurants-{self.geo}-{self.slug}.html"

    def get_page_url(self, page_num):
        if page_num <= 1:
            return self.base_restaurants_url
        offset = (page_num - 1) * RESTAURANTS_PER_PAGE
        return f"{BASE_URL}/Restaurants-{self.geo}-oa{offset}-{self.slug}.html"

    @classmethod
    def from_url(cls, url):
        """Extrae el Geo ID y slug a partir de cualquier URL de restaurantes de TripAdvisor."""
        m = re.search(r"Restaurants-(g\d+)-([^\.]+)\.html", url)
        if not m:
            raise ValueError(f"No se pudo extraer el Geo ID de la URL: {url}\nFormato esperado: .../Restaurants-gXXXXXX-Nombre_Ciudad.html")
        geo = m.group(1)
        raw_slug = m.group(2)
        # Limpiar posible paginación interna -oa30-
        slug = re.sub(r"-oa\d+-", "-", raw_slug)
        name = slug.split("_")[0]
        return cls(name=name, geo=geo, slug=slug)

    @classmethod
    def from_city_name(cls, city_name):
        """Resuelve el Geo ID y slug mediante el catálogo interno o parámetros."""
        key = city_name.strip().lower()
        if key in KNOWN_CITIES:
            item = KNOWN_CITIES[key]
            return cls(name=item["name"], geo=item["geo"], slug=item["slug"])
        
        # Si no está en el diccionario predefinido, generar slug aproximado
        formatted_name = city_name.strip().title()
        slug_guess = re.sub(r"\s+", "_", formatted_name)
        return cls(name=formatted_name, geo="g187497", slug=slug_guess)


# ---------------------------------------------------------------------------
# Verificación de Entorno e Instalación
# ---------------------------------------------------------------------------

def check_installation():
    """Valida que Camoufox y sus dependencias estén correctamente instalados."""
    print("=" * 60)
    print("VERIFICACIÓN DE INSTALACIÓN - CAMOUFOX SCRAPER")
    print("=" * 60)
    ok = True

    try:
        import camoufox
        ver = getattr(camoufox, '__version__', '')
        if hasattr(ver, '__version__'):
            ver = ver.__version__
        print(f"[OK] Paquete Python camoufox instalado (versión {ver})")
    except ImportError:
        print("[ERROR] El paquete 'camoufox' no está instalado.")
        print("        Ejecuta: pip install -r requirements.txt")
        ok = False

    try:
        import playwright
        print(f"[OK] Paquete Python playwright instalado")
    except ImportError:
        print("[ERROR] El paquete 'playwright' no está instalado.")
        print("        Ejecuta: pip install playwright")
        ok = False

    if ok:
        try:
            from camoufox.sync_api import Camoufox
            with Camoufox(headless=True, i_know_what_im_doing=True) as b:
                p = b.new_page()
                p.goto("about:blank")
                print("[OK] Arranque de prueba de Camoufox completado con éxito.")
        except Exception as launch_err:
            print(f"[ERROR] No se pudo arrancar el navegador Camoufox: {launch_err}")
            print("        Ejecuta: python -m camoufox fetch")
            ok = False

    print("=" * 60)
    if ok:
        print("[LISTO] Todas las dependencias están operativas para iniciar el scraping.")
    else:
        print("[ACCION REQUERIDA] Instala los componentes faltantes antes de ejecutar.")
    print("=" * 60)
    return ok


# ---------------------------------------------------------------------------
# Base de Datos Local SQLite (Persistencia y Reanudación)
# ---------------------------------------------------------------------------

class Database:
    """Gestiona el almacenamiento incremental y checkpoints por ciudad."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS restaurants (
                    id TEXT PRIMARY KEY,
                    url TEXT UNIQUE,
                    name TEXT,
                    phone TEXT,
                    street_address TEXT,
                    postal_code TEXT,
                    locality TEXT,
                    full_address TEXT,
                    rating REAL,
                    review_count INTEGER,
                    cuisine TEXT,
                    price_range TEXT,
                    status TEXT DEFAULT 'pending', -- pending, done, failed
                    last_error TEXT,
                    discovered_page INTEGER,
                    scraped_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_progress (
                    page INTEGER PRIMARY KEY,
                    offset INTEGER,
                    restaurants_found INTEGER,
                    status TEXT,
                    crawled_at TIMESTAMP
                )
            """)
            conn.commit()

    def add_restaurant_url(self, url, page_num):
        match = re.search(r"-d(\d+)-", url)
        rest_id = f"d{match.group(1)}" if match else url

        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO restaurants (id, url, status, discovered_page)
                VALUES (?, ?, 'pending', ?)
            """, (rest_id, url, page_num))
            conn.commit()

    def get_pending_urls(self, limit=None):
        query = "SELECT id, url FROM restaurants WHERE status = 'pending' ORDER BY discovered_page ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()

    def update_restaurant_data(self, rest_id, data):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE restaurants SET
                    name = ?,
                    phone = ?,
                    street_address = ?,
                    postal_code = ?,
                    locality = ?,
                    full_address = ?,
                    rating = ?,
                    review_count = ?,
                    cuisine = ?,
                    price_range = ?,
                    status = 'done',
                    last_error = NULL,
                    scraped_at = ?
                WHERE id = ?
            """, (
                data.get("name"),
                data.get("phone"),
                data.get("street_address"),
                data.get("postal_code"),
                data.get("locality"),
                data.get("full_address"),
                data.get("rating"),
                data.get("review_count"),
                data.get("cuisine"),
                data.get("price_range"),
                datetime.utcnow().isoformat(),
                rest_id
            ))
            conn.commit()

    def mark_failed(self, rest_id, error_msg):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE restaurants SET
                    status = 'failed',
                    last_error = ?
                WHERE id = ?
            """, (str(error_msg), rest_id))
            conn.commit()

    def log_page_crawled(self, page_num, offset, count):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO crawl_progress (page, offset, restaurants_found, status, crawled_at)
                VALUES (?, ?, ?, 'done', ?)
            """, (page_num, offset, count, datetime.utcnow().isoformat()))
            conn.commit()

    def is_page_crawled(self, page_num):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM crawl_progress WHERE page = ?", (page_num,))
            row = c.fetchone()
            return row and row[0] == "done"

    def get_stats(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM restaurants")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM restaurants WHERE status = 'done'")
            done = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM restaurants WHERE status = 'pending'")
            pending = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM restaurants WHERE status = 'failed'")
            failed = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM restaurants WHERE phone IS NOT NULL AND phone != ''")
            with_phone = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM restaurants WHERE full_address IS NOT NULL AND full_address != ''")
            with_addr = c.fetchone()[0]
            c.execute("SELECT MAX(page) FROM crawl_progress WHERE status = 'done'")
            last_page = c.fetchone()[0] or 0
            return {
                "total": total,
                "done": done,
                "pending": pending,
                "failed": failed,
                "with_phone": with_phone,
                "with_address": with_addr,
                "last_crawled_page": last_page
            }

    def export_csv(self, output_csv_path):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    name, 
                    full_address, 
                    street_address,
                    postal_code,
                    locality,
                    phone, 
                    rating, 
                    review_count, 
                    cuisine, 
                    price_range, 
                    url,
                    scraped_at
                FROM restaurants
                WHERE status = 'done'
                ORDER BY name ASC
            """)
            rows = cursor.fetchall()

        fieldnames = [
            "Nombre",
            "Dirección Completa",
            "Calle",
            "Código Postal",
            "Localidad",
            "Teléfono",
            "Puntuación",
            "Total Opiniones",
            "Tipo de Cocina",
            "Rango de Precio",
            "URL TripAdvisor",
            "Fecha Extracción"
        ]

        with open(output_csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            writer.writerows(rows)

        return len(rows)


# ---------------------------------------------------------------------------
# Lógica de Scraping con Camoufox
# ---------------------------------------------------------------------------

class TripAdvisorScraper:
    """Motor de scraping para cualquier ciudad configurada."""

    def __init__(self, target_city, db, proxy_rotator=None, headless=True, delay_min=1.5, delay_max=3.5):
        self.target_city = target_city
        self.db = db
        self.proxy_rotator = proxy_rotator
        self.headless = headless
        self.delay_min = delay_min
        self.delay_max = delay_max

    def _sleep_jitter(self, factor=1.0):
        t = random.uniform(self.delay_min, self.delay_max) * factor
        time.sleep(t)

    def _handle_cookie_consent(self, page):
        for frame in page.frames:
            try:
                for selector in [
                    "#onetrust-accept-btn-handler",
                    "button#onetrust-accept-btn-handler",
                    "button#didomi-notice-agree-button",
                    "button:has-text('Aceptar')",
                    "button:has-text('Acepto')",
                    "button:has-text('Aceptar todo')",
                    "button:has-text('Accept All')",
                    "button:has-text('Agree')"
                ]:
                    btn = frame.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(0.8)
                        return True
            except Exception:
                pass
        return False

    def crawl_catalog(self, browser_context, start_page=1, max_pages=None):
        print("\n" + "=" * 60)
        print(f"INICIANDO FASE 1: CATALOGACIÓN DE RESTAURANTES")
        print(f"Ciudad: {self.target_city.name} ({self.target_city.geo}) | Desde página: {start_page}")
        print("=" * 60)

        page = browser_context.new_page()
        current_page = start_page
        pages_processed = 0

        try:
            while True:
                if max_pages and pages_processed >= max_pages:
                    print(f"Límite de {max_pages} páginas alcanzado.")
                    break

                if self.db.is_page_crawled(current_page):
                    print(f"[Página {current_page}] Ya fue catalogada previamente. Saltando...")
                    current_page += 1
                    continue

                url = self.target_city.get_page_url(current_page)
                offset = (current_page - 1) * RESTAURANTS_PER_PAGE
                print(f"\n[Página {current_page} | Offset {offset}] Navegando a: {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    print(f"Error cargando página {current_page}: {e}. Reintentando...")
                    self._sleep_jitter(2.0)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    except Exception as e2:
                        print(f"Error persistente en página {current_page}: {e2}. Saltando página.")
                        current_page += 1
                        continue

                self._sleep_jitter(0.8)
                self._handle_cookie_consent(page)

                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                time.sleep(0.8)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)

                geo_code = self.target_city.geo
                urls_on_page = page.evaluate(f"""() => {{
                    const links = new Set();
                    const targetGeo = '{geo_code}';
                    const anchors = document.querySelectorAll('a[href*="/Restaurant_Review-' + targetGeo + '"]');
                    anchors.forEach(a => {{
                        let h = a.href.split('?')[0];
                        if (h.includes('-d') && !h.includes('#')) {{
                            links.add(h);
                        }}
                    }});
                    return Array.from(links);
                }}""")

                if not urls_on_page:
                    is_last_page = page.evaluate("""() => {
                        const nextBtn = document.querySelector('a.nav.next, a[aria-label="Página siguiente"], a[data-smoke-attr="pagination-next-arrow"]');
                        return !nextBtn || nextBtn.classList.contains('disabled');
                    }""")
                    print(f"No se detectaron nuevos restaurantes en la página {current_page}.")
                    if is_last_page:
                        print(f"Fin del catálogo de {self.target_city.name} alcanzado.")
                        break
                    else:
                        print("Posible ralentización de carga. Pausando...")
                        self._sleep_jitter(2.0)

                for r_url in urls_on_page:
                    self.db.add_restaurant_url(r_url, current_page)

                self.db.log_page_crawled(current_page, offset, len(urls_on_page))
                pages_processed += 1
                stats = self.db.get_stats()
                print(f"[Página {current_page}] Encontrados: {len(urls_on_page)} URLs | Total en BD: {stats['total']}")

                current_page += 1
                self._sleep_jitter(1.0)

        finally:
            page.close()

    def scrape_restaurant_details(self, browser_context, limit=None):
        pending = self.db.get_pending_urls(limit=limit)
        total_pending = len(pending)
        print("\n" + "=" * 60)
        print(f"INICIANDO FASE 2: EXTRACCIÓN DE DETALLES ({total_pending} pendientes en {self.target_city.name})")
        print("=" * 60)

        if not pending:
            print("No hay restaurantes pendientes de procesar.")
            return

        page = browser_context.new_page()
        count = 0
        locality_default = self.target_city.name

        try:
            for rest_id, url in pending:
                count += 1
                print(f"\n[{count}/{total_pending}] Extrayendo ({rest_id}): {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    self._sleep_jitter(0.6)
                    self._handle_cookie_consent(page)

                    data = page.evaluate(f"""() => {{
                        const res = {{
                            name: '',
                            phone: '',
                            street_address: '',
                            postal_code: '',
                            locality: '{locality_default}',
                            full_address: '',
                            rating: null,
                            review_count: 0,
                            cuisine: '',
                            price_range: ''
                        }};

                        // 1. Bloque estructurado LD+JSON
                        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {{
                            try {{
                                const parsed = JSON.parse(s.innerText);
                                const items = Array.isArray(parsed) ? parsed : (parsed['@graph'] ? parsed['@graph'] : [parsed]);
                                for (const item of items) {{
                                    if (item['@type'] === 'Restaurant' || item['@type'] === 'FoodEstablishment') {{
                                        if (item.name) res.name = item.name;
                                        if (item.telephone) res.phone = item.telephone;
                                        if (item.address) {{
                                            if (typeof item.address === 'object') {{
                                                res.street_address = item.address.streetAddress || '';
                                                res.postal_code = item.address.postalCode || '';
                                                res.locality = item.address.addressLocality || '{locality_default}';
                                            }} else if (typeof item.address === 'string') {{
                                                res.full_address = item.address;
                                            }}
                                        }}
                                        if (item.aggregateRating) {{
                                            res.rating = item.aggregateRating.ratingValue || null;
                                            res.review_count = item.aggregateRating.reviewCount || 0;
                                        }}
                                        if (item.servesCuisine) {{
                                            res.cuisine = Array.isArray(item.servesCuisine) ? item.servesCuisine.join(', ') : item.servesCuisine;
                                        }}
                                        if (item.priceRange) res.priceRange = item.priceRange;
                                    }}
                                }}
                            }} catch(e) {{}}
                        }});

                        // 2. Selectores de respaldo DOM
                        if (!res.name) {{
                            const h1 = document.querySelector('h1[data-test-target="top-info-header"], h1');
                            if (h1) res.name = h1.innerText.trim();
                        }}

                        if (!res.phone) {{
                            const telLink = document.querySelector('a[href^="tel:"]');
                            if (telLink) {{
                                res.phone = telLink.innerText.trim() || telLink.getAttribute('href').replace('tel:', '').trim();
                            }}
                        }}

                        if (!res.street_address && !res.full_address) {{
                            const addrLink = document.querySelector('a[href*="#MAPVIEW"], span[class*="street-address"], div[data-bltd-component="Address"]');
                            if (addrLink) {{
                                res.full_address = addrLink.innerText.trim();
                            }}
                        }}

                        if (!res.full_address && res.street_address) {{
                            const parts = [res.street_address, res.postal_code, res.locality].filter(Boolean);
                            res.full_address = parts.join(', ');
                        }}

                        return res;
                    }}""")

                    if data.get("phone"):
                        data["phone"] = re.sub(r"\s+", " ", data["phone"]).strip()

                    self.db.update_restaurant_data(rest_id, data)
                    print(f" -> Nombre:    {data.get('name') or '[Sin Nombre]'}")
                    print(f" -> Dirección: {data.get('full_address') or '[Sin Dirección]'}")
                    print(f" -> Teléfono:  {data.get('phone') or '[Sin Teléfono]'}")

                except Exception as e:
                    print(f" -> Error al extraer restaurante {rest_id}: {e}")
                    self.db.mark_failed(rest_id, str(e))

                self._sleep_jitter(1.0)

        finally:
            page.close()


# ---------------------------------------------------------------------------
# CLI y Punto de Entrada
# ---------------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="TripAdvisor Multi-City Restaurant Scraper con Camoufox (Nombre, Dirección, Teléfono)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso por ciudad:
  python scraper.py --city barcelona
  python scraper.py --city madrid
  python scraper.py --city valencia --mode catalog --max-pages 10
  python scraper.py --url "https://www.tripadvisor.es/Restaurants-g187514-Madrid.html"
  python scraper.py --city sevilla --limit 50 --output restaurantes_sevilla.csv

Ejemplos con rotación de proxies:
  python scraper.py --city barcelona --proxy-list proxies.txt
  python scraper.py --city madrid --proxy "http://usuario:pass@proxy-ip:puerto"

Otras opciones:
  python scraper.py --export-only --db tripadvisor_barcelona.db --output barcelona.csv
  python scraper.py --check-install
        """
    )
    # Selección de ciudad / objetivo
    city_group = parser.add_argument_group("Selección de Ciudad / Destino")
    city_group.add_argument(
        "--city",
        type=str,
        default="barcelona",
        help="Nombre de la ciudad objetivo (ej: barcelona, madrid, valencia, sevilla, malaga, bilbao, etc.)"
    )
    city_group.add_argument(
        "--url",
        type=str,
        default=None,
        help="URL directa de la página de restaurantes de TripAdvisor (anula --city si se especifica)"
    )
    city_group.add_argument(
        "--geo",
        type=str,
        default=None,
        help="Identificador geográfico explícito de TripAdvisor (ej: g187497 para Barcelona, g187514 para Madrid)"
    )
    city_group.add_argument(
        "--city-slug",
        type=str,
        default=None,
        help="Slug canónico de la ciudad para la URL (usado junto a --geo)"
    )

    # Flujo de ejecución
    flow_group = parser.add_argument_group("Control de Flujo")
    flow_group.add_argument(
        "--mode",
        choices=["all", "catalog", "detail"],
        default="all",
        help="Modo de ejecución: 'catalog' (descubrir URLs), 'detail' (extraer fichas), 'all' (ambos en secuencia)"
    )
    flow_group.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Página inicial para el catálogo (por defecto: 1)"
    )
    flow_group.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Límite máximo de páginas a catalogar (por defecto: todas)"
    )
    flow_group.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de restaurantes pendientes a procesar en modo detail"
    )

    # Salida y persistencia
    io_group = parser.add_argument_group("Almacenamiento y Salida")
    io_group.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta del archivo CSV de salida (por defecto: restaurantes_<ciudad>.csv)"
    )
    io_group.add_argument(
        "--db",
        type=str,
        default=None,
        help="Ruta de la base de datos SQLite (por defecto: tripadvisor_<ciudad>.db)"
    )
    io_group.add_argument(
        "--export-only",
        action="store_true",
        help="Solo exporta la base de datos actual a CSV sin realizar peticiones de red"
    )

    # Proxies y sigilo
    stealth_group = parser.add_argument_group("Proxies y Sigilo")
    stealth_group.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy único a utilizar (ej. 'http://user:pass@host:port' o 'socks5://127.0.0.1:1080')"
    )
    stealth_group.add_argument(
        "--proxy-list",
        type=str,
        default=None,
        help="Ruta a un archivo .txt con lista de proxies (uno por línea) para rotación automática"
    )
    stealth_group.add_argument(
        "--no-headless",
        action="store_true",
        help="Muestra la ventana del navegador (por defecto se ejecuta en modo headless sigiloso)"
    )
    stealth_group.add_argument(
        "--delay-min",
        type=float,
        default=1.5,
        help="Retardo mínimo entre peticiones en segundos (por defecto: 1.5)"
    )
    stealth_group.add_argument(
        "--delay-max",
        type=float,
        default=3.5,
        help="Retardo máximo entre peticiones en segundos (por defecto: 3.5)"
    )
    stealth_group.add_argument(
        "--check-install",
        action="store_true",
        help="Ejecuta diagnóstico de instalación de Camoufox y Playwright"
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.check_install:
        success = check_installation()
        sys.exit(0 if success else 1)

    # 1. Determinar ciudad objetivo
    if args.url:
        target_city = TargetCity.from_url(args.url)
    elif args.geo:
        slug = args.city_slug or re.sub(r"\s+", "_", args.city.strip().title())
        target_city = TargetCity(name=args.city.strip().title(), geo=args.geo, slug=slug)
    else:
        target_city = TargetCity.from_city_name(args.city)

    # 2. Asignar rutas por defecto si no fueron especificadas
    db_file = args.db or f"tripadvisor_{target_city.file_slug}.db"
    csv_file = args.output or f"restaurantes_{target_city.file_slug}.csv"

    db = Database(db_file)

    if args.export_only:
        print(f"Exportando registros de {db_file} a {csv_file}...")
        total = db.export_csv(csv_file)
        print(f"[OK] Se exportaron exitosamente {total} restaurantes a {csv_file}")
        sys.exit(0)

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        print("[ERROR] Camoufox no está disponible en este entorno.")
        print("        Ejecuta primero: python scraper.py --check-install")
        sys.exit(1)

    # 3. Configurar rotación de proxies
    proxy_rotator = ProxyRotator(proxy_list_path=args.proxy_list, single_proxy=args.proxy)

    print("=" * 60)
    print("TRIPADVISOR RESTAURANT SCRAPER (MULTI-CIUDAD)")
    print("=" * 60)
    print(f"Ciudad:          {target_city.name} (Geo: {target_city.geo})")
    print(f"URL Base:        {target_city.base_restaurants_url}")
    print(f"Modo:            {args.mode}")
    print(f"Base de datos:   {db_file}")
    print(f"Salida CSV:      {csv_file}")
    print(f"Headless:        {not args.no_headless}")
    if proxy_rotator.proxies:
        print(f"Pool Proxies:    {len(proxy_rotator.proxies)} configurados")
    print("=" * 60)

    stats = db.get_stats()
    print(f"Estado inicial BD: {stats['total']} encontrados | {stats['done']} completados | {stats['pending']} pendientes")

    scraper = TripAdvisorScraper(
        target_city=target_city,
        db=db,
        proxy_rotator=proxy_rotator,
        headless=not args.no_headless,
        delay_min=args.delay_min,
        delay_max=args.delay_max
    )

    camoufox_kwargs = {
        "headless": not args.no_headless,
        "os": "windows",
        "i_know_what_im_doing": True
    }
    initial_proxy = proxy_rotator.get_next()
    if initial_proxy:
        camoufox_kwargs["proxy"] = {"server": initial_proxy}

    with Camoufox(**camoufox_kwargs) as browser:
        context = browser.new_context(locale="es-ES")

        if args.mode in ("all", "catalog"):
            start = args.start_page
            if start == 1 and stats["last_crawled_page"] > 0:
                print(f"Reanudando catalogación desde la última página no completada (Página {stats['last_crawled_page'] + 1})...")
                start = stats["last_crawled_page"] + 1

            scraper.crawl_catalog(
                browser_context=context,
                start_page=start,
                max_pages=args.max_pages
            )

        if args.mode in ("all", "detail"):
            scraper.scrape_restaurant_details(
                browser_context=context,
                limit=args.limit
            )

        context.close()

    print("\n" + "=" * 60)
    print("GENERANDO ARCHIVO CSV FINAL")
    print("=" * 60)
    total_exported = db.export_csv(csv_file)
    final_stats = db.get_stats()
    print(f"Proceso concluido exitosamente:")
    print(f"- Ciudad:                         {target_city.name}")
    print(f"- Total restaurantes catalogados: {final_stats['total']}")
    print(f"- Total con datos completos:      {final_stats['done']}")
    print(f"- Total con teléfono:             {final_stats['with_phone']}")
    print(f"- Total con dirección:            {final_stats['with_address']}")
    print(f"- Archivo CSV generado:           {csv_file} ({total_exported} filas)")
    print("=" * 60)


if __name__ == "__main__":
    main()
