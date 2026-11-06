#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper_ipw.py - Motor de extraccion TripAdvisor sobre invisible_playwright.

Usa un motor Firefox parcheado a nivel C++ (invisible_playwright) con entrada
humanizada, en lugar de Camoufox, para atravesar DataDome cuando la huella del
navegador es el factor limitante.

Reutiliza la capa de persistencia (SQLite + exportacion CSV) de scraper.py,
por lo que el CSV resultante tiene exactamente el mismo esquema.

Autor: Marlon Sarduy Machado (UserZero075)
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

try:
    from scraper import Database, TargetCity, KNOWN_CITIES
except ImportError:
    sys.exit("[ERROR] Ejecuta este script desde el directorio del proyecto.")

BASE = "https://www.tripadvisor.es"
REST_ID_RE = re.compile(r"-d(\d+)-")


# ---------------------------------------------------------------------------
# Utilidades de extraccion
# ---------------------------------------------------------------------------

def extract_rest_id(url):
    m = REST_ID_RE.search(url)
    return f"d{m.group(1)}" if m else None


def slug_to_name(url):
    m = re.search(r"-Reviews-([^-]+(?:-[^-]+)*?)-([A-Z][a-z]+(?:_[A-Z][a-z]+)*)\.html", url)
    if not m:
        return ""
    return m.group(1).replace("_", " ").strip()


def pick_restaurant_ld(blocks, expect_id=None):
    """Elige el bloque LD+JSON del restaurante principal (no los tours)."""
    best, best_score = None, -1
    for raw in blocks:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        cands = data if isinstance(data, list) else [data]
        for c in cands:
            if not isinstance(c, dict):
                continue
            if c.get("@type") not in ("Restaurant", "FoodEstablishment", "LocalBusiness", "BarOrPub", "CafeOrCoffeeShop"):
                continue
            street = (c.get("address") or {}).get("streetAddress")
            phone = c.get("telephone")
            rating = (c.get("aggregateRating") or {}).get("ratingValue")
            score = sum([bool(street), bool(phone), bool(rating),
                         bool(c.get("servesCuisine")), bool(c.get("priceRange"))])
            if score > best_score:
                best, best_score = c, score
    return best if best_score >= 2 else None


def _s(v):
    """Normaliza valores LD+JSON que pueden venir como dict/lista."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        return _s(v.get("name") or v.get("@id") or "")
    if isinstance(v, list):
        return ", ".join(x for x in (_s(i) for i in v) if x)
    return str(v)


def wait_for_ld(page, max_ms=9000):
    """Espera a que aparezca un bloque ld+json con telefono (evita espera fija)."""
    waited = 0
    while waited < max_ms:
        try:
            n = page.eval_on_selector_all(
                'script[type="application/ld+json"]',
                "els => els.filter(e => e.textContent.includes('telephone')).length",
            )
            if n:
                return True
        except Exception:
            pass
        page.wait_for_timeout(400)
        waited += 400
    return False


def parse_detail(page, source_url, default_locality=None):
    """Devuelve dict con los campos del CSV o None si la ficha no es valida."""
    rest_id = extract_rest_id(source_url)
    final_url = page.url
    if rest_id and rest_id.replace("d", "-d") not in final_url and f"-{rest_id}-" not in final_url:
        # TripAdvisor sirvio otra ficha: descartar para no guardar datos ajenos
        return None

    blocks = page.eval_on_selector_all(
        'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
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

    # Fallback DOM
    text = page.evaluate("document.body.innerText")
    phone = None
    m = re.search(r"\+\d[\d\s().-]{7,}\d", text)
    if m:
        phone = m.group(0).strip()
    name = None
    try:
        name = page.eval_on_selector("h1", "e => e.innerText").strip()
    except Exception:
        pass
    if not name:
        return None
    return {
        "name": name, "phone": phone, "street_address": None, "postal_code": None,
        "locality": None, "full_address": None, "rating": None,
        "review_count": None, "cuisine": None, "price_range": None,
    }


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

class IPWCrawler:
    def __init__(self, browser, db, target, delay_min, delay_max,
                 page_delay_min, page_delay_max, batch_size, cool_min, cool_max,
                 geo_filter=None):
        self.browser = browser
        self.db = db
        self.target = target
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.page_delay_min = page_delay_min
        self.page_delay_max = page_delay_max
        self.batch_size = batch_size
        self.cool_min = cool_min
        self.cool_max = cool_max
        self.page = None
        self.counter = 0
        self.geo_filter = geo_filter

    # -- navegacion ---------------------------------------------------------
    def ensure_page(self):
        if self.page is None:
            self.page = self.browser.new_page()
        return self.page

    def human_pause(self, lo, hi):
        time.sleep(random.uniform(lo, hi))

    def scroll_like_human(self, seconds):
        page = self.ensure_page()
        end = time.time() + seconds
        while time.time() < end:
            step = random.randint(180, 520) * random.choice((-1, 1))
            try:
                page.evaluate(f"window.scrollBy({{top:{step}, behavior:'smooth'}})")
            except Exception:
                pass
            time.sleep(random.uniform(1.2, 2.6))

    def cooldown_if_needed(self):
        self.counter += 1
        if self.counter % self.batch_size == 0:
            pause = random.uniform(self.cool_min, self.cool_max)
            print(f"  [COOLDOWN] {self.counter} peticiones -> pausa {pause:.1f}s con scroll humano")
            self.scroll_like_human(pause)

    def assert_not_blocked(self):
        page = self.ensure_page()
        try:
            if len(page.frames) > 1 and "captcha-delivery" in page.frames[1].url:
                return False
        except Exception:
            pass
        return True

    # -- fase 1: catalogo ---------------------------------------------------
    def crawl_catalog(self, start_page=1, max_pages=None):
        print("=" * 66)
        print(f"FASE 1 - CATALOGO: {self.target.name}")
        print("=" * 66)
        page = self.ensure_page()
        offset = (start_page - 1) * 30
        page_no = start_page
        empty_streak = 0
        while True:
            if max_pages and page_no >= start_page + max_pages:
                break
            url = self.target.get_page_url(page_no)
            print(f"[Catalogo p{page_no} | oa{offset}] {url}")
            try:
                page.goto(url, timeout=60000)
            except Exception as e:
                print(f"  [ERROR] {type(e).__name__}: {e}")
                empty_streak += 1
                if empty_streak >= 3:
                    break
                self.human_pause(5, 9)
                continue
            page.wait_for_timeout(3500)

            anchors = page.eval_on_selector_all(
                'a[href*="Restaurant_Review-"]', "els => els.map(e => e.href)"
            )
            ids = {}
            for a in anchors:
                rid = extract_rest_id(a)
                if rid and rid not in ids:
                    ids[rid] = a.split("?")[0]
            new = 0
            for rid, u in ids.items():
                before = self.db.get_stats()["total"]
                self.db.add_restaurant_url(u, page_no)
                after = self.db.get_stats()["total"]
                if after > before:
                    new += 1
            total = self.db.get_stats()["total"]
            print(f"  -> {len(ids)} fichas en pagina, {new} nuevas, total BD: {total}")

            if len(ids) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    print("  Fin del catalogo (paginas vacias consecutivas).")
                    break
            else:
                empty_streak = 0

            offset += 30
            page_no += 1
            self.human_pause(self.page_delay_min, self.page_delay_max)

        return self.db.get_stats()

    # -- fase 2: fichas -----------------------------------------------------
    def scrape_details(self, limit=None):
        print("=" * 66)
        print("FASE 2 - EXTRACCION DE FICHAS")
        print("=" * 66)
        page = self.ensure_page()
        pending = self.db.get_pending_urls(limit=None)
        if self.geo_filter:
            pending = [(rid, u) for rid, u in pending if self.geo_filter in u]
        if limit:
            pending = pending[:limit]
        print(f"Pendientes a procesar: {len(pending)}")
        done = 0
        for idx, (rid, url) in enumerate(pending, 1):
            print(f"[{idx}/{len(pending)}] {rid}")
            data = None
            for attempt in (1, 2):
                try:
                    page.goto(url, timeout=60000)
                    wait_for_ld(page, max_ms=9000)
                    page.wait_for_timeout(random.randint(250, 700))
                    if not self.assert_not_blocked():
                        print("  [BLOQUEO] challenge detectado, cooldown largo")
                        self.scroll_like_human(random.uniform(35, 55))
                        continue
                    data = parse_detail(page, url, default_locality=self.target.name)
                    if data:
                        break
                except Exception as e:
                    print(f"  [ERROR intento {attempt}] {type(e).__name__}: {e}")
                    self.human_pause(4, 8)
            if data:
                self.db.update_restaurant_data(rid, data)
                done += 1
                print(f"  OK  {data.get('name')} | {data.get('phone')} | "
                      f"{data.get('rating')} ({data.get('review_count')})")
            else:
                print("  [SIN DATOS] se deja pendiente para reintento")
            self.cooldown_if_needed()
            self.human_pause(self.delay_min, self.delay_max)
        return done


def main():
    ap = argparse.ArgumentParser(description="TripAdvisor scraper sobre invisible_playwright")
    ap.add_argument("--city", default="barcelona")
    ap.add_argument("--url")
    ap.add_argument("--db", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--mode", choices=["all", "catalog", "detail"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--delay-min", type=float, default=1.8)
    ap.add_argument("--delay-max", type=float, default=3.6)
    ap.add_argument("--page-delay-min", type=float, default=3.0)
    ap.add_argument("--page-delay-max", type=float, default=6.0)
    ap.add_argument("--batch-size", type=int, default=18)
    ap.add_argument("--batch-cooldown-min", type=float, default=20.0)
    ap.add_argument("--batch-cooldown-max", type=float, default=38.0)
    ap.add_argument("--export-only", action="store_true")
    ap.add_argument("--geo-filter", default=None,
                    help="Procesa solo fichas cuyo Geo ID coincida (ej: g187529)")
    args = ap.parse_args()

    target = TargetCity.from_url(args.url) if args.url else TargetCity.from_city_name(args.city)
    db_file = args.db or f"tripadvisor_{target.file_slug}.db"
    csv_file = args.output or f"restaurantes_{target.file_slug}.csv"
    db = Database(db_file)

    if args.export_only:
        n = db.export_csv(csv_file)
        print(f"[OK] {n} filas -> {csv_file}")
        return

    from invisible_playwright import InvisiblePlaywright

    print("=" * 66)
    print("TRIPADVISOR SCRAPER - MOTOR invisible_playwright")
    print("=" * 66)
    print(f"Ciudad:   {target.name} ({target.geo})")
    print(f"BD:       {db_file}")
    print(f"CSV:      {csv_file}")
    print(f"Delays:   {args.delay_min}-{args.delay_max}s | paginas "
          f"{args.page_delay_min}-{args.page_delay_max}s | lote {args.batch_size}")
    print("=" * 66)
    print("BD inicial:", db.get_stats())

    with InvisiblePlaywright(humanize=True, headless=False, locale="es-ES") as browser:
        cr = IPWCrawler(browser, db, target,
                        args.delay_min, args.delay_max,
                        args.page_delay_min, args.page_delay_max,
                        args.batch_size, args.batch_cooldown_min, args.batch_cooldown_max,
                        geo_filter=args.geo_filter)
        if args.mode in ("all", "catalog"):
            cr.crawl_catalog(start_page=1, max_pages=args.max_pages)
        if args.mode in ("all", "detail"):
            cr.scrape_details(limit=args.limit)

    n = db.export_csv(csv_file)
    stats = db.get_stats()
    print("=" * 66)
    print(f"Total catalogados: {stats['total']} | completos: {stats['done']} | "
          f"con telefono: {stats['with_phone']} | con direccion: {stats['with_address']}")
    print(f"CSV: {csv_file} ({n} filas)")
    print("=" * 66)


if __name__ == "__main__":
    main()
