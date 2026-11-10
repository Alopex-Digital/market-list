"""Website scanning: what the company does, contact details, optional proof signals.

Runs in plain Python threads, so it does not use Claude's web tools or limits.
"""
import re, json, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from core import http_get, html_to_text, kw_hits, domain_of, strip_accents

# Words that mark contact / about / team pages in many European languages.
CONTACT_WORDS = ["contact", "kontakt", "yhteys", "yhteystied", "kontakti", "kontaktai", "kapcsolat", "contatt",
                 "contacto", "about", "meista", "meist", "tietoa", "par-mums", "par mums", "apie", "uber-uns",
                 "ueber-uns", "about-us", "team", "tiimi", "henkilo", "henkilö", "people", "staff", "komanda",
                 "kollektiv", "om-oss", "om oss", "medarbet", "o-nas", "o nas", "chi-siamo", "qui-sommes",
                 "who-we-are", "impressum", "yritys", "company", "uznemums", "firma", "ettevottest", "meist"]

GENERIC_LOCAL = {"info", "sales", "office", "hello", "hei", "moi", "myynti", "tilaukset", "tilaus", "asiakaspalvelu",
                 "contact", "kontakt", "kontakti", "post", "posti", "mail", "email", "pasts", "birojs", "admin",
                 "support", "service", "orders", "order", "pardosana", "tirdznieciba", "shop", "webshop", "kauppa",
                 "verkkokauppa", "toimisto", "laskutus", "invoice", "invoices", "billing", "reception", "marketing",
                 "markkinointi", "info.lv", "info.fi", "kundservice", "kundtjanst", "tellimus", "muuk", "myyntitiimi",
                 "promo", "print", "paino", "studio", "design", "hr", "jobs", "rekry", "careers", "press", "media",
                 "noreply", "no-reply", "privacy", "gdpr", "tietosuoja", "dpo", "accounting", "kirjanpito"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_TEL_RE = re.compile(r'href=["\']tel:([^"\']+)["\']', re.I)
PHONE_TXT_RE = re.compile(r"(?:\+\d{2,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{2,4}(?:[\s\-]?\d{2,4})?")
BAD_EMAIL_END = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
BAD_EMAIL_DOM = ("example.com", "sentry.io", "wixpress.com", "domain.com", "email.com", "yourdomain", "sentry-next",
                 "godaddy.com", "w3.org", "schema.org")


def clean_emails(raw, site_domain):
    out = []
    for e in raw:
        e = e.strip(".,;:()[]<>\"'").lower()
        if e.endswith(BAD_EMAIL_END) or any(b in e for b in BAD_EMAIL_DOM):
            continue
        if re.search(r"@\d+x\.", e) or len(e) > 80:
            continue
        if e not in out:
            out.append(e)
    # own-domain first
    out.sort(key=lambda x: 0 if site_domain and x.endswith("@" + site_domain) or (site_domain and site_domain in x.split("@")[1]) else 1)
    return out[:15]


def email_kind(email):
    local = email.split("@")[0].lower()
    base = re.sub(r"[\d_\-.]+$", "", local)
    if local in GENERIC_LOCAL or base in GENERIC_LOCAL:
        return "generic"
    if re.match(r"^[a-zÀ-ɏ]+[._\-][a-zÀ-ɏ]+$", strip_accents(local)):
        return "named"
    if re.match(r"^[a-z]{3,15}$", local):
        return "maybe-named"   # e.g. "jaana@" – first name only, or a word
    return "other"


def name_from_email(email):
    local = email.split("@")[0]
    parts = re.split(r"[._\-]", local)
    if len(parts) == 2 and all(p.isalpha() and len(p) > 1 for p in parts):
        return " ".join(p.capitalize() for p in parts)
    return ""


def clean_phones(html, text):
    phones = []
    for p in PHONE_TEL_RE.findall(html):
        p = re.sub(r"[^\d+]", "", p)
        if 7 <= len(p.replace("+", "")) <= 15 and p not in phones:
            phones.append(p)
    if not phones:
        for m in PHONE_TXT_RE.findall(text):
            digits = re.sub(r"\D", "", m)
            if 8 <= len(digits) <= 13 and (m.strip().startswith("+") or m.strip().startswith("0")):
                p = re.sub(r"\s+", " ", m.strip())
                if p not in phones:
                    phones.append(p)
            if len(phones) >= 3:
                break
    return phones[:5]


def pick_pages(base_url, html, limit=4):
    links = re.findall(r'href=["\']([^"\'#]+)["\']', html, re.I)
    dom = domain_of(base_url)
    picked = []
    for href in links:
        u = urljoin(base_url, href)
        if domain_of(u) != dom:
            continue
        path = strip_accents(urlparse(u).path.lower())
        if any(w in path for w in CONTACT_WORDS) and u not in picked and not re.search(r"\.(pdf|jpg|png|zip)$", path):
            picked.append(u)
    # shortest paths first (main contact/about pages rather than deep articles)
    picked.sort(key=lambda x: len(urlparse(x).path))
    return picked[:limit]


def fetch_home(url):
    """Try https, http, with/without www. Returns (final_url, html) or (None, '')."""
    d = domain_of(url)
    if not d:
        return None, ""
    tried_dead = False
    for u in (f"https://{d}", f"https://www.{d}", f"http://{d}", f"http://www.{d}"):
        st, html, final = http_get(u, timeout=10, retries=0)
        if st and st < 400 and len(html) > 200:
            return final, html
        if st == 0:
            if tried_dead:          # two connection failures in a row: the host is down, stop trying
                break
            tried_dead = True
    return None, ""


def sitemap_urls(base, max_maps=6, max_urls=30000):
    """Collect page URLs from sitemap(s); used only for proof signals."""
    seen, urls = set(), []
    queue = [urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml"), urljoin(base, "/wp-sitemap.xml")]
    st, robots, _ = http_get(urljoin(base, "/robots.txt"), timeout=10)
    if st == 200:
        queue = re.findall(r"(?im)^sitemap:\s*(\S+)", robots) + queue
    n = 0
    while queue and n < max_maps and len(urls) < max_urls:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm); n += 1
        st, xml, _ = http_get(sm, timeout=20, max_bytes=8_000_000)
        if st != 200 or "<" not in xml:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        for l in locs:
            if l.endswith(".xml") or "sitemap" in l.lower():
                # product sitemaps first – they carry product codes
                if "product" in l.lower() or "tuote" in l.lower() or "prece" in l.lower():
                    queue.insert(0, l)
                else:
                    queue.append(l)
            else:
                urls.append(l)
    return urls


def proof_hits(text, signals):
    found = {}
    for sig in signals or []:
        total = 0
        for pat in sig.get("patterns", []):
            total += len(re.findall(pat, text, re.I))
        if total >= sig.get("min_hits", 1):
            found[sig["name"]] = total
    return found


def scan_one(company, site_keywords, proof_signals=None, deep_proof=False):
    url = company.get("website")
    res = {"ok": False, "t": time.strftime("%Y-%m-%d")}
    final, html = fetch_home(url)
    if not final:
        res["error"] = "site not reachable"
        return res
    res["ok"] = True
    res["final_url"] = final
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    desc = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html)
    lang = re.search(r'(?is)<html[^>]+lang=["\']([a-zA-Z\-]+)', html)
    pages = [(final, html)]
    for u in pick_pages(final, html):
        st, h, f = http_get(u, timeout=10, retries=0)
        if st and st < 400 and h:
            pages.append((f, h))
    all_html = "\n".join(h for _, h in pages)
    texts = [html_to_text(h) for _, h in pages]
    all_text = "\n".join(texts)
    home_text = texts[0]
    res["title"] = re.sub(r"\s+", " ", title.group(1)).strip()[:150] if title else ""
    res["description"] = (desc.group(1).strip()[:300] if desc else "")
    res["lang"] = lang.group(1) if lang else ""
    res["snippet"] = re.sub(r"\s+", " ", home_text)[:500]
    res["pages"] = [u for u, _ in pages]
    res["kw"] = kw_hits(all_text + " " + res["title"] + " " + res["description"], site_keywords)
    dom = domain_of(final)
    mails = EMAIL_RE.findall(all_html.replace("&#64;", "@").replace("[at]", "@").replace("(at)", "@"))
    res["emails"] = clean_emails(mails, dom)
    res["phones"] = clean_phones(all_html, all_text)
    if proof_signals:
        corpus = all_html
        if deep_proof:
            urls = sitemap_urls(final)
            res["sitemap_urls"] = len(urls)
            corpus += "\n" + "\n".join(urls)
        res["proof"] = proof_hits(corpus, proof_signals)
    return res


def scan_many(companies, site_keywords, proof_signals=None, deep_proof=False, threads=10, on_done=None):
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futs = {ex.submit(scan_one, c, site_keywords, proof_signals, deep_proof): c for c in companies}
        for f in as_completed(futs):
            c = futs[f]
            try:
                c["scan"] = f.result()
            except Exception as e:
                c["scan"] = {"ok": False, "error": str(e)[:200]}
            with lock:
                done += 1
                if on_done:
                    on_done(done, len(companies))
