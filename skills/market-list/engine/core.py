"""Shared helpers: project storage, HTTP, name and domain matching.

A project is one folder. Everything the run knows lives in plain files there,
so a run can stop at any moment and continue later:

  project.json    country, profile, settings, stage log
  companies.json  one record per company (the master list)
  people.json     named contacts
  cache/          downloaded registry files (safe to delete)
"""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.error, ssl, gzip, io
from urllib.parse import urlparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SSL_CTX = ssl.create_default_context()
SSL_LAX = ssl.create_default_context(); SSL_LAX.check_hostname = False; SSL_LAX.verify_mode = ssl.CERT_NONE

# ---------------------------------------------------------------- storage

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Project:
    def __init__(self, folder, write=True):
        self.dir = os.path.abspath(os.path.expanduser(folder))
        self.meta_path = os.path.join(self.dir, "project.json")
        self.comp_path = os.path.join(self.dir, "companies.json")
        self.people_path = os.path.join(self.dir, "people.json")
        if not os.path.exists(self.meta_path):
            sys.exit(f"No project at {self.dir}. Start one with: ml.py new --project {folder} --country XX --profile FILE")
        self.meta = load_json(self.meta_path, {})
        self.companies = load_json(self.comp_path, [])
        self.people = load_json(self.people_path, [])
        self.profile = self.meta["profile"]
        self.country = self.meta["country"]
        self.cache = os.path.join(self.dir, "cache")
        os.makedirs(self.cache, exist_ok=True)
        if write:
            self._lock()

    def _lock(self):
        """One writing command per project at a time (two at once would overwrite each other's work)."""
        import atexit
        lock = os.path.join(self.dir, ".lock")
        if os.path.exists(lock):
            try:
                pid = int(open(lock).read().strip() or 0)
                os.kill(pid, 0)
                sys.exit(f"Another command (pid {pid}) is still working on this project. Wait for it to finish, then run again.")
            except (ValueError, ProcessLookupError, PermissionError):
                pass   # stale lock from a crashed run
        with open(lock, "w") as f:
            f.write(str(os.getpid()))
        atexit.register(lambda: os.path.exists(lock) and os.remove(lock))

    # country block of the profile (keywords etc.)
    @property
    def cp(self):
        return self.profile.get("countries", {}).get(self.country, {})

    def save(self):
        save_json(self.comp_path, self.companies)
        save_json(self.people_path, self.people)
        save_json(self.meta_path, self.meta)

    def log(self, stage, msg):
        self.meta.setdefault("log", []).append({"t": time.strftime("%Y-%m-%d %H:%M"), "stage": stage, "msg": msg})
        self.meta.setdefault("stages", {})[stage] = time.strftime("%Y-%m-%d %H:%M")
        print(f"[{stage}] {msg}")

    def next_id(self):
        n = self.meta.get("seq", 0) + 1
        self.meta["seq"] = n
        return f"{self.country}{n:05d}"

    # ---- index helpers
    def find(self, reg_no=None, domain=None, name=None):
        for c in self.companies:
            if reg_no and c.get("reg_no") and norm_reg(c["reg_no"]) == norm_reg(reg_no):
                return c
        if domain:
            for c in self.companies:
                if c.get("website") and domain_of(c["website"]) == domain:
                    return c
        if name:
            n = norm_name(name)
            if n:
                for c in self.companies:
                    if n in (norm_name(c.get("legal_name")), norm_name(c.get("brand"))):
                        return c
        return None

    def upsert(self, rec, source):
        """Add a company or merge into an existing one (matched by reg no, domain, name)."""
        dom = domain_of(rec.get("website")) if rec.get("website") else None
        c = self.find(rec.get("reg_no"), dom, rec.get("legal_name") or rec.get("brand"))
        if c is None:
            c = {"id": self.next_id(), "country": self.country, "sources": []}
            self.companies.append(c)
            created = True
        else:
            created = False
        for k, v in rec.items():
            if v in (None, "", [], {}):
                continue
            if k == "note" and c.get("note") and v not in c["note"]:
                c["note"] = c["note"] + "; " + v
            elif k == "aliases":
                c["aliases"] = sorted(set(c.get("aliases", [])) | set(v))
            elif not c.get(k):
                c[k] = v
        if source not in c["sources"]:
            c["sources"].append(source)
        return c, created


def new_project(folder, country, profile):
    folder = os.path.abspath(os.path.expanduser(folder))
    os.makedirs(os.path.join(folder, "cache"), exist_ok=True)
    meta_path = os.path.join(folder, "project.json")
    if os.path.exists(meta_path):
        sys.exit(f"A project already exists at {folder}. Use another folder or continue it.")
    meta = {"country": country.upper(), "profile": profile, "created": time.strftime("%Y-%m-%d %H:%M"),
            "stages": {}, "log": [], "seq": 0}
    save_json(meta_path, meta)
    save_json(os.path.join(folder, "companies.json"), [])
    save_json(os.path.join(folder, "people.json"), [])
    return folder

# ---------------------------------------------------------------- HTTP

def http_get(url, timeout=20, binary=False, headers=None, retries=1, lax_ssl=True, max_bytes=None):
    """GET with a browser user agent. Returns (status, text_or_bytes, final_url)."""
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en,fi;q=0.8,lv;q=0.8,et;q=0.7", "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries + 1):
        for ctx in ([SSL_CTX, SSL_LAX] if lax_ssl else [SSL_CTX]):
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                    data = r.read(max_bytes) if max_bytes else r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        try:
                            data = gzip.decompress(data)
                        except Exception:
                            pass
                    if binary:
                        return r.status, data, r.geturl()
                    cs = r.headers.get_content_charset() or "utf-8"
                    return r.status, data.decode(cs, "ignore"), r.geturl()
            except urllib.error.HTTPError as e:
                return e.code, "", url
            except ssl.SSLError as e:
                last = e
                continue
            except Exception as e:
                last = e
                break
        if attempt < retries:
            time.sleep(1.5)
    return 0, "", url


def download(url, path, min_age_hours=20):
    """Download a big file once; reuse it if it is fresh."""
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < min_age_hours * 3600:
        return path
    print(f"  downloading {url} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600, context=SSL_CTX) as r, open(path + ".part", "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(path + ".part", path)
    return path

# ---------------------------------------------------------------- text helpers

LEGAL_FORMS = r"\b(oy|oyj|ab|ky|tmi|ay|osk|ry|sia|as|ou|oü|aps|a/s|gmbh|ltd|limited|llc|inc|sp\.? ?z ?o\.? ?o\.?|s\.?r\.?o\.?|uab|ab|asa|aps|bv|nv|srl|sarl|sas|sa|spa|ag|kg|ohg|plc|lp|i\/s|k\/s)\b"

def strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def norm_name(s):
    if not s:
        return ""
    s = strip_accents(str(s).lower())
    s = re.sub(r"sabiedriba ar ierobezotu atbildibu|akciju sabiedriba|individualais komersants", " ", s)
    s = re.sub(LEGAL_FORMS, " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_reg(s):
    return re.sub(r"[^0-9A-Za-z]", "", str(s or "")).upper()

def domain_of(url):
    if not url:
        return ""
    u = str(url).strip()
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    try:
        host = urlparse(u).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    return host[4:] if host.startswith("www.") else host

def site_url(url):
    d = domain_of(url)
    return f"https://{d}" if d else ""

def html_to_text(html):
    import html as _h
    t = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _h.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

def kw_hits(text, keywords):
    """Count keyword occurrences (case/accent-insensitive). Keywords may be regexes when wrapped in /../."""
    low = strip_accents(text.lower())
    hits = {}
    for kw in keywords or []:
        if kw.startswith("/") and kw.endswith("/") and len(kw) > 2:
            n = len(re.findall(kw[1:-1], text, re.I))
        else:
            n = low.count(strip_accents(kw.lower()))
        if n:
            hits[kw] = n
    return hits

def name_matches(name, keywords):
    low = " " + strip_accents(str(name).lower()) + " "
    for kw in keywords or []:
        k = strip_accents(kw.lower())
        if kw.startswith("/") and kw.endswith("/"):
            if re.search(kw[1:-1], name, re.I):
                return kw
        elif k in low:
            return kw
    return None
