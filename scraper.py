#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TripAdvisor Barcelona Scraper
=============================
Extractor automatizado de restaurantes de Barcelona en TripAdvisor utilizando
Camoufox Anti-Detect (Firefox parcheado con huella de navegación realista).

Campos extraídos:
- Nombre
- Dirección (calle, código postal, localidad)
- Teléfono
- Rating y número de opiniones
- Tipo de cocina y rango de precio
- URL de la ficha

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

# URL base oficial de restaurantes en Barcelona en TripAdvisor España
BASE_URL = "https://www.tripadvisor.es"
CITY_RESTAURANTS_URL = "https://www.tripadvisor.es/Restaurants-g187497-Barcelona_Catalonia.html"
CITY_CODE = "g187497"
RESTAURANTS_PER_PAGE = 30


# ---------------------------------------------------------------------------
# Verificación de Entorno e Instalación
# ---------------------------------------------------------------------------

def check_installation():
    """Valida que Camoufox y sus dependencias estén correctamente instalados."""
    print("=" * 60)
    print("VERIFICACIÓN DE INSTALACIÓN - CAMOUFOX SCRAPER")
    print("=" * 60)
    ok = True

    # 1. Paquete camoufox
    try:
        import camoufox
        ver = getattr(camoufox, '__version__', '')
        if hasattr(ver, '__version__'):
            ver = ver.__version__
        print(f"[OK] Paquete Python camoufox instalado (versión {ver})")
    except ImportError:
        print("[ERROR] El paquete 'camoufox' no está instalado.")
        print("        Ejecuta: pip install camoufox playwright beautifulsoup4")
        ok = False

    # 2. Paquete playwright
    try:
        import playwright
        print(f"[OK] Paquete Python playwright instalado")
    except ImportError:
        print("[ERROR] El paquete 'playwright' no está instalado.")
        print("        Ejecuta: pip install playwright")
        ok = False

    # 3. Binario del navegador Camoufox
    if ok:
        try:
            from camoufox.pkgman import get_installed_browser_path
            path = get_installed_browser_path()
            if path and os.path.exists(path):
                print(f"[OK] Navegador Camoufox encontrado en:\n     {path}")
            else:
                print("[ERROR] El binario del navegador Camoufox no está descargado.")
                print("        Ejecuta: python -m camoufox fetch")
                ok = False
        except Exception as e:
            print(f"[AVISO] Comprobación de binario alternativa: {e}")
            try:
                from camoufox.sync_api import Camoufox
                with Camoufox(headless=True, i_know_what_im_doing=True) as b:
                    p = b.new_page()
                    p.goto("about:blank")
                    print("[OK] Arranque de prueba de Camoufox completado con éxito.")
            except Exception as launch_err:
                print(f"[ERROR] No se pudo arrancar Camoufox: {launch_err}")
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
    """Gestiona el almacenamiento incremental y checkpoints del scraping."""

    def __init__(self, db_path="tripadvisor_barcelona.db"):
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
        """Registra una URL de restaurante si no existe."""
        # Extraer ID canónico (ej. d1234567)
        match = re.search(r"-d(\d+)-", url)
        rest_id = f"d{match.group(1)}" if match else url

        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO restaurants (id, url, status, discovered_page)
                VALUES (?, ?, 'pending', ?)
            """, (rest_id, url, page_num))
            conn.commit()

    def get_pending_urls(self, limit=None):
        """Retorna lista de URLs pendientes por extraer detalle."""
        query = "SELECT id, url FROM restaurants WHERE status = 'pending' ORDER BY discovered_page ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()

    def update_restaurant_data(self, rest_id, data):
        """Actualiza los datos completos de un restaurante."""
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
        """Marca una URL con fallo para permitir reintentos posteriores."""
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
        """Retorna estadísticas de avance."""
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
        """Exporta todos los registros procesados a formato CSV con UTF-8 BOM."""
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
    """Scraper robusto de TripAdvisor con Camoufox."""

    def __init__(self, db, headless=True, proxy=None, delay_min=2.0, delay_max=4.5):
        self.db = db
        self.headless = headless
        self.proxy = proxy
        self.delay_min = delay_min
        self.delay_max = delay_max

    def _sleep_jitter(self, factor=1.0):
        t = random.uniform(self.delay_min, self.delay_max) * factor
        time.sleep(t)

    def _handle_cookie_consent(self, page):
        """Acepta banners de cookies de OneTrust, Didomi o diálogo de GDPR."""
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
                        time.sleep(1.0)
                        return True
            except Exception:
                pass
        return False

    def build_list_url(self, page_num):
        """Genera la URL canónica de TripAdvisor para una página de restaurantes."""
        if page_num <= 1:
            return CITY_RESTAURANTS_URL
        offset = (page_num - 1) * RESTAURANTS_PER_PAGE
        return f"{BASE_URL}/Restaurants-{CITY_CODE}-oa{offset}-Barcelona_Catalonia.html"

    def crawl_catalog(self, browser_context, start_page=1, max_pages=None):
        """
        Fase 1: Recorre las páginas de listado y extrae todas las URLs de restaurantes.
        """
        print("\n" + "=" * 60)
        print(f"INICIANDO FASE 1: CATALOGACIÓN DE RESTAURANTES (Página {start_page} en adelante)")
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

                url = self.build_list_url(current_page)
                offset = (current_page - 1) * RESTAURANTS_PER_PAGE
                print(f"\n[Página {current_page} | Offset {offset}] Navegando a: {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    print(f"Error cargando página {current_page}: {e}. Reintentando con pausa...")
                    self._sleep_jitter(2.0)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    except Exception as e2:
                        print(f"Error persistente en página {current_page}: {e2}. Saltando página.")
                        current_page += 1
                        continue

                self._sleep_jitter(0.8)
                self._handle_cookie_consent(page)

                # Scroll progresivo para forzar carga perezosa de tarjetas
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                time.sleep(0.8)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)

                # Extraer enlaces a fichas de restaurantes
                urls_on_page = page.evaluate("""() => {
                    const links = new Set();
                    // Buscar enlaces canónicos de restaurantes de Barcelona
                    const anchors = document.querySelectorAll('a[href*="/Restaurant_Review-g187497"]');
                    anchors.forEach(a => {
                        let h = a.href.split('?')[0];
                        if (h.includes('-d') && !h.includes('#')) {
                            links.add(h);
                        }
                    });
                    return Array.from(links);
                }""")

                if not urls_on_page:
                    # Detectar si llegamos al final del catálogo
                    is_last_page = page.evaluate("""() => {
                        const nextBtn = document.querySelector('a.nav.next, a[aria-label="Página siguiente"], a[data-smoke-attr="pagination-next-arrow"]');
                        return !nextBtn || nextBtn.classList.contains('disabled');
                    }""")
                    print(f"No se detectaron restaurantes en la página {current_page}.")
                    if is_last_page:
                        print("Fin del catálogo de restaurantes de Barcelona alcanzado.")
                        break
                    else:
                        print("Posible ralentización o bloqueo. Pausando...")
                        self._sleep_jitter(2.0)

                new_count = 0
                for r_url in urls_on_page:
                    self.db.add_restaurant_url(r_url, current_page)
                    new_count += 1

                self.db.log_page_crawled(current_page, offset, len(urls_on_page))
                pages_processed += 1
                stats = self.db.get_stats()
                print(f"[Página {current_page}] Encontrados: {len(urls_on_page)} URLs | Total acumulado en BD: {stats['total']}")

                current_page += 1
                self._sleep_jitter(1.0)

        finally:
            page.close()

    def scrape_restaurant_details(self, browser_context, limit=None):
        """
        Fase 2: Visita cada restaurante pendiente y extrae nombre, dirección y teléfono.
        """
        pending = self.db.get_pending_urls(limit=limit)
        total_pending = len(pending)
        print("\n" + "=" * 60)
        print(f"INICIANDO FASE 2: EXTRACCIÓN DE DETALLES ({total_pending} restaurantes pendientes)")
        print("=" * 60)

        if not pending:
            print("No hay restaurantes pendientes de procesar.")
            return

        page = browser_context.new_page()
        count = 0

        try:
            for rest_id, url in pending:
                count += 1
                print(f"\n[{count}/{total_pending}] Extrayendo ({rest_id}): {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    self._sleep_jitter(0.6)
                    self._handle_cookie_consent(page)

                    # Extracción con script JS evaluado directamente en el contexto del navegador
                    data = page.evaluate("""() => {
                        const res = {
                            name: '',
                            phone: '',
                            street_address: '',
                            postal_code: '',
                            locality: 'Barcelona',
                            full_address: '',
                            rating: null,
                            review_count: 0,
                            cuisine: '',
                            price_range: ''
                        };

                        // 1. Intentar LD+JSON (Schema.org / Restaurant)
                        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                            try {
                                const parsed = JSON.parse(s.innerText);
                                const items = Array.isArray(parsed) ? parsed : (parsed['@graph'] ? parsed['@graph'] : [parsed]);
                                for (const item of items) {
                                    if (item['@type'] === 'Restaurant' || item['@type'] === 'FoodEstablishment') {
                                        if (item.name) res.name = item.name;
                                        if (item.telephone) res.phone = item.telephone;
                                        if (item.address) {
                                            if (typeof item.address === 'object') {
                                                res.street_address = item.address.streetAddress || '';
                                                res.postal_code = item.address.postalCode || '';
                                                res.locality = item.address.addressLocality || 'Barcelona';
                                            } else if (typeof item.address === 'string') {
                                                res.full_address = item.address;
                                            }
                                        }
                                        if (item.aggregateRating) {
                                            res.rating = item.aggregateRating.ratingValue || null;
                                            res.review_count = item.aggregateRating.reviewCount || 0;
                                        }
                                        if (item.servesCuisine) {
                                            res.cuisine = Array.isArray(item.servesCuisine) ? item.servesCuisine.join(', ') : item.servesCuisine;
                                        }
                                        if (item.priceRange) res.priceRange = item.priceRange;
                                    }
                                }
                            } catch(e) {}
                        });

                        // 2. Fallbacks de DOM si el LD+JSON vino incompleto
                        if (!res.name) {
                            const h1 = document.querySelector('h1[data-test-target="top-info-header"], h1');
                            if (h1) res.name = h1.innerText.trim();
                        }

                        // Teléfono vía enlace tel: o bloque de contacto
                        if (!res.phone) {
                            const telLink = document.querySelector('a[href^="tel:"]');
                            if (telLink) {
                                res.phone = telLink.innerText.trim() || telLink.getAttribute('href').replace('tel:', '').trim();
                            }
                        }

                        // Dirección física desde enlace de mapa o etiquetas de dirección
                        if (!res.street_address && !res.full_address) {
                            const addrLink = document.querySelector('a[href*="#MAPVIEW"], span[class*="street-address"], div[data-bltd-component="Address"]');
                            if (addrLink) {
                                res.full_address = addrLink.innerText.trim();
                            }
                        }

                        // Componer dirección completa legible
                        if (!res.full_address && res.street_address) {
                            const parts = [res.street_address, res.postal_code, res.locality].filter(Boolean);
                            res.full_address = parts.join(', ');
                        }

                        return res;
                    }""")

                    # Limpieza y normalización de teléfono
                    if data.get("phone"):
                        # Normalizar formato telefónico eliminando espacios excesivos
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
        description="TripAdvisor Barcelona Scraper con Camoufox (Nombre, Dirección, Teléfono)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python scraper.py --mode all
  python scraper.py --mode catalog --max-pages 10
  python scraper.py --mode detail --limit 50
  python scraper.py --export-only --output barcelona_restaurantes.csv
  python scraper.py --check-install
        """
    )
    parser.add_argument(
        "--mode",
        choices=["all", "catalog", "detail"],
        default="all",
        help="Modo de ejecución: 'catalog' (descubrir URLs), 'detail' (extraer fichas), 'all' (ambos en secuencia)"
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Página inicial para el catálogo (por defecto: 1)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Límite máximo de páginas a catalogar (por defecto: todas)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de restaurantes pendientes a procesar en modo detail"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="restaurantes_barcelona.csv",
        help="Ruta del archivo CSV de salida (por defecto: restaurantes_barcelona.csv)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="tripadvisor_barcelona.db",
        help="Ruta de la base de datos SQLite (por defecto: tripadvisor_barcelona.db)"
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy a utilizar (ej. 'http://user:pass@host:port' o 'socks5://127.0.0.1:1080')"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Muestra la ventana del navegador (por defecto se ejecuta en modo headless sigiloso)"
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=1.5,
        help="Retardo mínimo entre peticiones en segundos (por defecto: 1.5)"
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=3.5,
        help="Retardo máximo entre peticiones en segundos (por defecto: 3.5)"
    )
    parser.add_argument(
        "--check-install",
        action="store_true",
        help="Ejecuta diagnóstico de instalación de Camoufox y Playwright"
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Solo exporta la base de datos actual a CSV sin realizar peticiones de red"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.check_install:
        success = check_installation()
        sys.exit(0 if success else 1)

    db = Database(args.db)

    if args.export_only:
        print(f"Exportando registros de {args.db} a {args.output}...")
        total = db.export_csv(args.output)
        print(f"[OK] Se exportaron exitosamente {total} restaurantes a {args.output}")
        sys.exit(0)

    # Verificar disponibilidad de Camoufox
    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        print("[ERROR] Camoufox no está disponible en este entorno.")
        print("        Ejecuta primero: python scraper.py --check-install")
        sys.exit(1)

    print("=" * 60)
    print("TRIPADVISOR BARCELONA SCRAPER")
    print("=" * 60)
    print(f"Objetivo:        {CITY_RESTAURANTS_URL}")
    print(f"Modo:            {args.mode}")
    print(f"Base de datos:   {args.db}")
    print(f"Salida CSV:      {args.output}")
    print(f"Headless:        {not args.no_headless}")
    if args.proxy:
        print(f"Proxy:           {args.proxy}")
    print("=" * 60)

    stats = db.get_stats()
    print(f"Estado inicial BD: {stats['total']} encontrados | {stats['done']} completados | {stats['pending']} pendientes")

    scraper = TripAdvisorScraper(
        db=db,
        headless=not args.no_headless,
        proxy=args.proxy,
        delay_min=args.delay_min,
        delay_max=args.delay_max
    )

    camoufox_kwargs = {
        "headless": not args.no_headless,
        "os": "windows",
        "i_know_what_im_doing": True
    }
    if args.proxy:
        camoufox_kwargs["proxy"] = {"server": args.proxy}

    with Camoufox(**camoufox_kwargs) as browser:
        context = browser.new_context(locale="es-ES")

        # 1. Modo catálogo o all
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

        # 2. Modo detalle o all
        if args.mode in ("all", "detail"):
            scraper.scrape_restaurant_details(
                browser_context=context,
                limit=args.limit
            )

        context.close()

    # Exportación final automática a CSV
    print("\n" + "=" * 60)
    print("GENERANDO ARCHIVO CSV FINAL")
    print("=" * 60)
    total_exported = db.export_csv(args.output)
    final_stats = db.get_stats()
    print(f"Proceso concluido exitosamente:")
    print(f"- Total restaurantes catalogados: {final_stats['total']}")
    print(f"- Total con datos completos:      {final_stats['done']}")
    print(f"- Total con teléfono:             {final_stats['with_phone']}")
    print(f"- Total con dirección:            {final_stats['with_address']}")
    print(f"- Archivo CSV generado:           {args.output} ({total_exported} filas)")
    print("=" * 60)


if __name__ == "__main__":
    main()
