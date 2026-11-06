#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper_fast.py - Motor híbrido de alta velocidad para TripAdvisor (~80-100 fichas/min).

Arquitectura:
1. Utiliza `invisible_playwright` una sola vez para resolver la huella de DataDome
   y obtener una cookie de sesión válida (`datadome`) y el User-Agent exacto de Firefox.
2. Utiliza `curl_cffi` (impersonación TLS firefox133) para consultar directamente
   las URLs de detalle a nivel HTTP nativo (~300-500ms por ficha).
3. Parsea los metadatos estructurados Schema.org (`application/ld+json`) en memoria,
   obteniendo teléfono, dirección completa normalizada, valoración, cocina y rango de precio.
4. Si DataDome detecta la sesión (403 o captcha), renueva la cookie automáticamente
   volviendo a abrir el navegador durante 2-3 segundos y continúa sin interrupciones.

Autor: Marlon Sarduy Machado (UserZero075)
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from curl_cffi import requests
from invisible_playwright import InvisiblePlaywright

try:
    from scraper import Database, TargetCity, KNOWN_CITIES
    from scraper_ipw import pick_restaurant_ld, _s, slug_to_name, IPWCrawler
except ImportError:
    sys.exit("[ERROR] Ejecuta este script desde el directorio del proyecto.")

BASE = "https://www.tripadvisor.es"
REST_ID_RE = re.compile(r"-d(\d+)-")


def extract_rest_id(url):
    m = REST_ID_RE.search(url)
    return f"d{m.group(1)}" if m else None


def parse_detail_html(html, source_url, default_locality=None):
    """Extrae datos de la ficha desde el HTML crudo sin overhead de DOM."""
    blocks = re.findall(
        r'<script[^>]*type=[\x27"]application/ld\+json[\x27"][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    ld = pick_restaurant_ld(blocks)
    if ld:
        addr = ld.get("address") or {}
        agg = ld.get("aggregateRating") or {}
        cuisine = ld.get("servesCuisine")
        if isinstance(cuisine, list):
            cuisine = ", ".join(_s(x) for x in cuisine)
        cuisine = _s(cuisine) or None
        street = _s(addr.get("streetAddress"))
        pc = _s(addr.get("postalCode"))
        loc = _s(addr.get("addressLocality")) or (default_locality or "")
        country = _s(addr.get("addressCountry"))
        if country.upper() == "ES":
            country = "España"
        full = ", ".join(x for x in [street, f"{pc} {loc}".strip(), country] if x)
        return {
            "name": _s(ld.get("name")) or slug_to_name(source_url),
            "phone": _s(ld.get("telephone")) or None,
            "street_address": street,
            "postal_code": pc,
            "locality": loc,
            "full_address": full.strip(", "),
            "rating": _s(agg.get("ratingValue")) or None,
            "review_count": agg.get("reviewCount") or agg.get("ratingCount"),
            "cuisine": cuisine,
            "price_range": _s(ld.get("priceRange")) or None,
        }

    # Fallback si no hay bloque de schema pero hay teléfono en texto
    m = re.search(r"\+\d[\d\s().-]{7,}\d", html)
    phone = m.group(0).strip() if m else None
    name_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    name = re.sub(r"<[^>]+>", "", name_m.group(1)).strip() if name_m else slug_to_name(source_url)
    if name:
        return {
            "name": name,
            "phone": phone,
            "street_address": None,
            "postal_code": None,
            "locality": default_locality,
            "full_address": default_locality or "",
            "rating": None,
            "review_count": None,
            "cuisine": None,
            "price_range": None,
        }
    return None


class FastSession:
    """Administra la sesión HTTP rápida de curl_cffi con refresco asistido por navegador."""

    def __init__(self, target_url):
        self.target_url = target_url
        self.ua = None
        self.dd_cookie = None
        self.session = None
        self.refresh_session()

    def refresh_session(self):
        print("[FAST] Adquiriendo/Renovando sesión legítima con invisible_playwright...", flush=True)
        with InvisiblePlaywright(humanize=True, headless=False, locale="es-ES") as browser:
            page = browser.new_page()
            page.goto(self.target_url, timeout=45000)
            time.sleep(2.5)
            cookies = page.context.cookies()
            self.ua = page.evaluate("navigator.userAgent")
            self.dd_cookie = next((c["value"] for c in cookies if c["name"] == "datadome"), None)

        if not self.dd_cookie:
            print("[WARN] No se encontró cookie datadome en la sesión.", flush=True)

        headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "Referer": "https://www.tripadvisor.es/",
        }
        self.session = requests.Session(impersonate="firefox133")
        self.session.headers.update(headers)
        if self.dd_cookie:
            self.session.cookies.update({"datadome": self.dd_cookie})
        print("[FAST] Sesión HTTP lista con Firefox 133 TLS impersonation.", flush=True)

    def fetch(self, url):
        """Descarga una URL devolviendo (html, success). Si hay 403 renueva y reintenta."""
        for attempt in range(2):
            try:
                resp = self.session.get(url, timeout=12)
                if resp.status_code == 200 and "captcha-delivery" not in resp.text:
                    return resp.text, True
                if resp.status_code == 403 or "captcha-delivery" in resp.text:
                    print(f"[FAST] Desafío DataDome detectado ({resp.status_code}). Renovando sesión...", flush=True)
                    self.refresh_session()
                    time.sleep(1)
            except Exception as e:
                print(f"[FAST-ERR] Intento {attempt+1}: {e}", flush=True)
                self.refresh_session()
                time.sleep(1.5)
        return None, False


def scrape_details_fast(db, target, limit=5000, geo_filter=None, delay=0.22, batch_save=25):
    """Bucle principal de extracción ultrarrápida."""
    rows = db.get_pending_urls()
    if geo_filter:
        rows = [r for r in rows if geo_filter in r[1]]

    total_pending = len(rows)
    to_scrape = rows[:limit] if limit else rows
    print(f"\n[FAST] Iniciando extracción: {len(to_scrape)} fichas (pendientes totales: {total_pending})")

    fast_session = FastSession(target.base_restaurants_url)
    done_count = 0
    t0 = time.time()
    last_lap = time.time()
    lap_done = 0

    for i, (rid, url) in enumerate(to_scrape, 1):
        html, ok = fast_session.fetch(url)
        if ok and html:
            data = parse_detail_html(html, url, default_locality=target.name)
            if data:
                db.update_restaurant_data(rid, data)
                done_count += 1
                lap_done += 1
                name_str = (data.get("name") or "")[:30]
                tel = data.get("phone") or "Sin teléfono"
                print(f"[{done_count}/{len(to_scrape)}] OK {name_str} | {tel}", flush=True)
            else:
                db.mark_failed(rid, "Datos no válidos")
        else:
            db.mark_failed(rid, "Error de red/bloqueo")

        # Estadísticas de velocidad periódicas
        now = time.time()
        if now - last_lap >= 30.0:
            elapsed_min = (now - t0) / 60.0
            overall_rpm = done_count / elapsed_min if elapsed_min > 0 else 0
            lap_rpm = lap_done / ((now - last_lap) / 60.0)
            print(f"--- [RITMO] Total: {overall_rpm:.1f} fichas/min | Últimos 30s: {lap_rpm:.1f} fichas/min | Done: {done_count} ---", flush=True)
            last_lap = now
            lap_done = 0

        time.sleep(random.uniform(delay * 0.85, delay * 1.15))

    total_time = time.time() - t0
    final_rpm = done_count / (total_time / 60.0) if total_time > 0 else 0
    print(f"\n[FAST] Finalizado: {done_count} fichas extraídas en {total_time/60.0:.2f} min ({final_rpm:.1f} fichas/min)")


def main():
    ap = argparse.ArgumentParser(description="Scraper TripAdvisor Ultra-Rápido (~80-100 fichas/min)")
    ap.add_argument("--city", default="barcelona", help="Nombre de ciudad (ej: barcelona, valencia)")
    ap.add_argument("--url", default=None, help="URL directa de catálogo")
    ap.add_argument("--limit", type=int, default=5000, help="Límite de fichas")
    ap.add_argument("--max-pages", type=int, default=200, help="Páginas de catálogo a rastrear")
    ap.add_argument("--delay", type=float, default=0.22, help="Retardo base entre peticiones HTTP (segundos)")
    ap.add_argument("--db", default="tripadvisor.db", help="Base de datos SQLite")
    ap.add_argument("--output", default=None, help="Archivo CSV de salida")
    ap.add_argument("--geo-filter", default=None, help="Filtrar por Geo ID en URL (ej: g187497)")
    ap.add_argument("--mode", choices=["all", "catalog", "detail"], default="all")
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    target = TargetCity.from_url(args.url) if args.url else TargetCity.from_city_name(args.city)
    db_file = os.path.abspath(args.db)
    csv_file = os.path.abspath(args.output) if args.output else os.path.abspath(f"restaurantes_{target.slug}.csv")
    db = Database(db_file)

    if args.export_only:
        n = db.export_csv(csv_file)
        print(f"[EXPORT] {n} restaurantes exportados a {csv_file}")
        return

    # Si se pide catálogo, usamos el motor visual de invisible_playwright
    if args.mode in ("all", "catalog"):
        print("[FAST] Rastreando catálogo con invisible_playwright...")
        with InvisiblePlaywright(humanize=True, headless=False, locale="es-ES") as browser:
            cr = IPWCrawler(browser, db, target, 1.2, 2.4, 2.0, 4.0, 40, 10, 20, geo_filter=args.geo_filter)
            cr.crawl_catalog(start_page=1, max_pages=args.max_pages)

    # Si se pide detalle, usamos la extracción rápida con curl_cffi
    if args.mode in ("all", "detail"):
        scrape_details_fast(db, target, limit=args.limit, geo_filter=args.geo_filter, delay=args.delay)

    n = db.export_csv(csv_file)
    print(f"\n[EXPORT] Proceso completo. {n} restaurantes guardados en:\n  {csv_file}")


if __name__ == "__main__":
    main()
