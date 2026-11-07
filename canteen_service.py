"""
canteen_service.py - iCanteen Scraper & Image Matcher for SPSE Jecna C3a
Fetches the school lunch menu from iCanteen, cleans meal names, searches high-res dish photos,
and provides both static JSON output and a REST API endpoint (GET /api/menu).
"""

import sys
import os
import re
import json
import time
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Default configuration
DEFAULT_CANTEEN_URL = "https://strav.nasejidelna.cz/0341/login"
DEFAULT_PRICE = "40.00 Kč"
DEFAULT_LOCATION = "Ječná"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canteen_menu.json")
STATIC_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "canteen_menu.json")

# In-memory image cache to avoid repeating search queries for the same dish
IMAGE_CACHE = {}


def normalize_canteen_url(url: str) -> str:
    """Corrects common URL typos (e.g. nasajdelna -> nasejidelna, 3341 -> 0341)."""
    if not url:
        return DEFAULT_CANTEEN_URL
    url = url.replace("nasajdelna.cz", "nasejidelna.cz")
    url = url.replace("/3341/", "/0341/")
    if url.endswith("/3341"):
        url = url.replace("/3341", "/0341/login")
    if "faces/secured/month.jsp" in url or "month.jsp" in url:
        # iCanteen public menu is published directly on /login without needing a session
        url = url.split("/faces/")[0] + "/login"
    return url


def clean_food_query_for_image(raw_name: str) -> str:
    """
    Cleans a meal name for image search:
    - Strips allergens, weights, soup prefixes when appropriate
    - Keeps the main culinary focus
    - Appends 'jídlo' for high-quality food photography results
    """
    name = raw_name.strip()

    # Remove parentheses and allergen brackets (e.g. "(1, 6, 7)" or "[1, 7]")
    name = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', ' ', name)

    # Remove common food portion/weight specs (e.g. "150g", "100 g", "1ks", "2 ks")
    name = re.sub(r'\b\d+\s*(?:g|dkg|kg|ks|porce|ml|l)\b', ' ', name, flags=re.IGNORECASE)

    # Split parts by comma or slash
    parts = [p.strip() for p in re.split(r'[,/;+]', name) if p.strip()]

    if not parts:
        return "jídlo oběd"

    # Known soup indicators in Czech canteens
    soup_keywords = [
        "polévka", "vývar", "krém", "čočková", "bramboračka", "gulášová",
        "hrachová", "zeleninová", "hovězí", "slepičí", "kuřecí", "rybí",
        "kaldoun", "uzená", "celerová", "krupicí", "pórková", "květáková",
        "francouzská", "dršťková", "rajčatová", "boršč", "drožďová"
    ]

    # If first part looks like a soup and we have subsequent main dishes, prioritize main dish
    target = parts[0]
    if len(parts) > 1:
        first_lower = parts[0].lower()
        is_soup = any(kw in first_lower for kw in soup_keywords)
        if is_soup:
            # Main dish is typically part 1 (or part 1 + part 2)
            if len(parts) >= 3:
                target = f"{parts[1]} {parts[2]}"
            else:
                target = parts[1]
        else:
            target = f"{parts[0]} {parts[1]}"

    # Clean multiple whitespaces and trailing punctuation
    target = re.sub(r'[^\w\s\u00C0-\u017F-]', ' ', target)
    target = ' '.join(target.split())

    return f"{target} jídlo"


def search_image_for_meal(meal_name: str) -> str:
    """
    Finds a high-res dish photo:
    1. Checks cache
    2. Bing Image Search (no API key required, reliable)
    3. Google Custom Search (if GOOGLE_SEARCH_API_KEY & GOOGLE_SEARCH_CX are set)
    4. Unsplash API (if UNSPLASH_ACCESS_KEY is set)
    5. Fallback curated food photo
    """
    search_query = clean_food_query_for_image(meal_name)
    if search_query in IMAGE_CACHE:
        return IMAGE_CACHE[search_query]

    # Check Google Custom Search API if configured
    g_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    g_cx = os.environ.get("GOOGLE_SEARCH_CX")
    if g_key and g_cx:
        try:
            url = f"https://www.googleapis.com/customsearch/v1?key={g_key}&cx={g_cx}&q={urllib.parse.quote(search_query)}&searchType=image&num=1&safe=active"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                if items and "link" in items[0]:
                    img_url = items[0]["link"]
                    IMAGE_CACHE[search_query] = img_url
                    return img_url
        except Exception as e:
            print(f"[canteen_service] Google search error: {e}", file=sys.stderr)

    # Check Unsplash API if configured
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if unsplash_key:
        try:
            url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(search_query)}&per_page=1&client_id={unsplash_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                if results and "urls" in results[0] and "regular" in results[0]["urls"]:
                    img_url = results[0]["urls"]["regular"]
                    IMAGE_CACHE[search_query] = img_url
                    return img_url
        except Exception as e:
            print(f"[canteen_service] Unsplash error: {e}", file=sys.stderr)

    # Direct Bing Image Search scraping (zero-config, high quality)
    try:
        bing_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(search_query)}&form=HDRSC2&first=1"
        req = urllib.request.Request(bing_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8"
        })
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Extract high-res media url from bing results
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', html)
            if not matches:
                matches = re.findall(r'\"murl\":\"(https?://[^\"]+)\"', html)
            for m in matches:
                # Filter out suspicious or bad extensions
                if any(ext in m.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", "photo", "upload", "img"]):
                    IMAGE_CACHE[search_query] = m
                    return m
            if matches:
                IMAGE_CACHE[search_query] = matches[0]
                return matches[0]
    except Exception as e:
        print(f"[canteen_service] Bing search error for '{search_query}': {e}", file=sys.stderr)

    # Fallback placeholder food photo from Unsplash
    fallback_url = "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80"
    IMAGE_CACHE[search_query] = fallback_url
    return fallback_url


def fetch_icanteen_menu(canteen_url: str = DEFAULT_CANTEEN_URL, location_filter: str = DEFAULT_LOCATION, fetch_images: bool = True):
    """
    Scrapes iCanteen HTML and returns structured daily menus matching the requested schema.
    """
    url = normalize_canteen_url(canteen_url)
    print(f"[canteen_service] Fetching menu from: {url}")

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "cs-CZ,cs;q=0.9"
    })

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as err:
        print(f"[canteen_service] Failed to fetch iCanteen: {err}", file=sys.stderr)
        return []

    # Parse days: <div id="day-YYYY-MM-DD" ...>
    day_matches = list(re.finditer(r'<div id=\"day-(\d{4}-\d{2}-\d{2})\".*?</article>', html, re.DOTALL))
    print(f"[canteen_service] Found {len(day_matches)} days in calendar.")

    results = []

    for dm in day_matches:
        date_str = dm.group(1)
        day_block = dm.group(0)

        # Extract weekday title (e.g. "pondělí 09.11.2026")
        title_m = re.search(r'<div id=\"day-\d{4}-\d{2}-\d{2}\"[^>]*>(.*?)</div>', day_block, re.DOTALL)
        formatted_day = ""
        if title_m:
            formatted_day = " ".join(re.sub(r'<.*?>|&nbsp;', ' ', title_m.group(1)).split())

        containers = day_block.split('<div class="container">')[1:]
        meals_for_day = []

        for container in containers:
            # Check location (Sokolská / Štěpánská / Ječná)
            loc_m = re.search(r'<(?:span|div)[^>]*>(Sokolská|Štěpánská|Ječná)</', container)
            location = loc_m.group(1) if loc_m else ""

            # If location_filter is set and not empty, check match
            if location_filter and location and location_filter.lower() not in location.lower():
                continue

            # Meal category/number (Oběd 1, Oběd 2)
            num_m = re.search(r'Oběd\s*(\d+)', container)
            meal_num = num_m.group(1) if num_m else "1"
            meal_id = f"obid-{meal_num}"

            # Text content of the meal
            col_m = re.search(r'<div class=\"column jidelnicekItem.*?>(.*?)</div>', container, re.DOTALL)
            if not col_m:
                continue

            raw_col = col_m.group(1)

            # Extract allergens
            allergens = []
            for alg_m in re.finditer(r'title=\"([^\"]+)\">(\d+)</span>', raw_col):
                allergens.append({
                    "code": alg_m.group(2),
                    "description": alg_m.group(1)
                })

            # Clean meal title (strip sub tags and inner HTML)
            cleaned_html = re.sub(r'<sub>.*?</sub>', '', raw_col, flags=re.DOTALL)
            meal_name = " ".join(re.sub(r'<.*?>', ' ', cleaned_html).split())

            # Skip empty entries (e.g. days far in advance with empty menu)
            if not meal_name:
                continue

            # Fetch image
            image_url = ""
            if fetch_images:
                image_url = search_image_for_meal(meal_name)

            meal_item = {
                "id": meal_id,
                "name": meal_name,
                "imageUrl": image_url,
                "price": DEFAULT_PRICE,
                "category": f"Oběd {meal_num}",
                "location": location or DEFAULT_LOCATION,
                "allergens": allergens
            }
            meals_for_day.append(meal_item)

        if meals_for_day:
            results.append({
                "date": date_str,
                "formattedDate": formatted_day,
                "meals": meals_for_day
            })

    return results


def save_menu_to_file(menu_data, target_file=CACHE_FILE):
    """Saves structured menu to JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)
    print(f"[canteen_service] Saved {len(menu_data)} days to {target_file}")


class CanteenRequestHandler(BaseHTTPRequestHandler):
    """Lightweight REST API handler (GET /api/menu)."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/menu":
            query_params = urllib.parse.parse_qs(parsed.query)
            target_date = query_params.get("date", [None])[0]

            # Read from cache file if available
            data = []
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = []

            # If cache is empty, fetch live
            if not data:
                data = fetch_icanteen_menu(fetch_images=True)
                save_menu_to_file(data)

            # Filter by date if requested
            response_payload = data
            if target_date:
                match = next((d for d in data if d["date"] == target_date), None)
                response_payload = match if match else {"date": target_date, "meals": []}

            body = json.dumps(response_payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


def run_server(port=8082):
    server = HTTPServer(("0.0.0.0", port), CanteenRequestHandler)
    print(f"[canteen_service] REST API server listening at http://0.0.0.0:{port}/api/menu")
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SPSE Jecna C3a iCanteen Menu Service")
    parser.add_argument("--fetch", action="store_true", help="Fetch menu, match images, and save to JSON")
    parser.add_argument("--server", action="store_true", help="Run REST API server")
    parser.add_argument("--port", type=int, default=8082, help="Port for REST API server")
    parser.add_argument("--url", type=str, default=DEFAULT_CANTEEN_URL, help="iCanteen URL")
    parser.add_argument("--no-images", action="store_true", help="Skip image fetching")
    args = parser.parse_args()

    if args.fetch or not args.server:
        print("[canteen_service] Fetching and processing menu...")
        data = fetch_icanteen_menu(canteen_url=args.url, fetch_images=not args.no_images)
        save_menu_to_file(data, CACHE_FILE)
        save_menu_to_file(data, STATIC_CACHE_FILE)
        print(f"[canteen_service] Done. Sample day 1 output:")
        if data:
            print(json.dumps(data[0], ensure_ascii=False, indent=2))

    if args.server:
        run_server(args.port)
