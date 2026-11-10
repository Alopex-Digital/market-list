"""Latvia.

Registry:   Uzņēmumu reģistrs open data (data.gov.lv register.csv), no key.
Industry:   VID tax data carries each company's main NACE code.
Money:      VID open data: taxes paid + average staff per year (last 2 closed years) and per quarter;
            firmas.lv public profile for the newest full year (same VID figures), website and phone.
People:     board members (officers.csv, names only).
"""
import os, re, csv, time, html as _h
from core import download, http_get, norm_name, domain_of, name_matches

INFO = {
    "name": "Latvia", "language": "Latvian (Russian also common)",
    "registry": "Uzņēmumu reģistrs open data (data.gov.lv)",
    "money_column": "Taxes paid {year} (thousand €)",
    "money_note": "Taxes paid and average staff from VID (State Revenue Service) open data and firmas.lv.",
}

URLS = {
    "register": "https://data.gov.lv/dati/dataset/4de9697f-850b-45ec-8bba-61fa09ce932f/resource/25e80bf3-f107-4ab4-89ef-251b5b9374e9/download/register.csv",
    "officers": "https://data.gov.lv/dati/dataset/096c7a47-33cd-4dc9-a876-2c86e86230fd/resource/e665114a-73c2-4375-9470-55874b4cfa6b/download/officers.csv",
    "taxes": "https://data.gov.lv/dati/dataset/5ed74664-b49d-4b28-aacb-040931646e9b/resource/a42d6e8c-1768-4939-ba9b-7700d4f1dd3a/download/pdb_nm_komersantu_samaksato_nodoklu_kopsumas_odata.csv",
    "taxes_q": "https://data.gov.lv/dati/dataset/364f3fa8-916f-48fe-9c81-12f13adb35f3/resource/9117ca92-7858-41cc-8c78-d5241ae5fcec/download/pdb_samaksato_nodoklu_kopsummas_cet.csv",
}
COMMERCIAL = {"SIA", "AS", "IK", "KS", "PS", "ARL", "FIL", "UZN", "ZEM", "KB", "SE", "EEIG", "UZ"}


def _file(p, key):
    return download(URLS[key], os.path.join(p.cache, f"lv_{key}.csv"), min_age_hours=24 * 7)


def _register(p):
    with open(_file(p, "register"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            yield r


def _nace(p):
    """regcode -> {year: {nace, tax, staff}} from VID yearly file."""
    out = {}
    with open(_file(p, "taxes"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["Registracijas_kods"], {})[r["Taksacijas_gads"]] = {
                "nace": r["Pamatdarbibas_NACE_kods"], "tax": _num(r["Samaksato_VID_administreto_nodoklu_kopsumma_tukst_EUR"]),
                "staff": _num(r["Videjais_nodarbinato_personu_skaits_cilv"])}
    return out


def _num(s):
    try:
        return float(str(s).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return None


def _status(r):
    if r.get("terminated"):
        return "closed (removed from register " + r["terminated"] + ")"
    return "active"


LEGAL_SHORT = [("Sabiedrība ar ierobežotu atbildību", "SIA"), ("Akciju sabiedrība", "AS"),
               ("Individuālais komersants", "IK"), ("Komandītsabiedrība", "KS"), ("Pilnsabiedrība", "PS")]


def short_legal(name):
    for long, short in LEGAL_SHORT:
        name = name.replace(long, short)
    return re.sub(r"\s+", " ", name).strip()


def _record(r, why, nace=None):
    brand = r.get("name_in_quotes") or r.get("name")
    return {"legal_name": short_legal(r["name"]), "brand": brand.title() if brand.isupper() else brand, "reg_no": r["regcode"],
            "city": (r.get("address") or "").split(",")[0].strip(), "status": _status(r),
            "industry_code": nace or "", "registry_match": why, "registered": r.get("registered", "")}


def sweep(p):
    cp = p.cp
    kws = cp.get("name_keywords", [])
    weak = cp.get("name_keywords_weak", [])
    neg = cp.get("name_exclude", [])
    codes = [str(c).replace(".", "") for c in cp.get("industry_codes", [])]
    min_staff = cp.get("industry_min_staff", 1)
    nace = _nace(p)
    added = by_code = 0
    cutoff = str(int(time.strftime("%Y")) - 3)
    for r in _register(p):
        if r.get("type") not in COMMERCIAL:
            continue
        if r.get("terminated") and r["terminated"][:4] < cutoff:
            continue                                      # long-closed companies are noise
        nm = r.get("name", "")
        hit = name_matches(nm, kws)
        if hit and name_matches(nm, neg):
            hit = None
        years = nace.get(r["regcode"], {})
        last = years[max(years)] if years else {}
        weak_hit = None if hit else name_matches(nm, weak)
        if hit:
            p.upsert(_record(r, f"name contains '{hit}'", last.get("nace")), "registry-name")
            added += 1
        elif weak_hit and not r.get("terminated") and last and (last.get("staff") or 0) >= 1:
            p.upsert(_record(r, f"name contains '{weak_hit}' (weak word, website must confirm)", last.get("nace")), "registry-weak")
            added += 1
        elif codes and last and any(last["nace"].startswith(c) for c in codes) and not r.get("terminated"):
            if (last.get("staff") or 0) >= min_staff:
                p.upsert(_record(r, f"industry code {last['nace']}", last.get("nace")), "registry-industry")
                by_code += 1
    p.log("registry", f"{added} by name keywords + {by_code} by industry code from the Latvian registry")


def lookup(p, companies):
    want = {}
    for c in companies:
        for nm in [c.get("brand"), c.get("legal_name")] + c.get("aliases", []):
            n = norm_name(nm)
            if n and len(n) > 2:
                want.setdefault(n, c)
    hits = 0
    for r in _register(p):
        for nm in (r.get("name"), r.get("name_in_quotes")):
            c = want.get(norm_name(nm))
            if c is not None and not c.get("reg_no") and not (r.get("terminated") and r["terminated"][:4] < "2020"):
                for k, v in _record(r, "matched by name").items():
                    if v and not c.get(k):
                        c[k] = v
                hits += 1
                break
    return hits


# ------------------------------------------------------------ money

def firmas(reg_no):
    """Taxes paid (k€) and average staff for the last 3 years, website and phone from firmas.lv."""
    st, html, url = http_get(f"https://www.firmas.lv/lv/uznemumi/meklet?q={reg_no}", timeout=25)
    m = re.search(r'href="(/lv/uznemumi/[^"/]+/' + reg_no + ')"', html or "")
    if not m:
        return None
    st, html, url = http_get("https://www.firmas.lv" + m.group(1), timeout=25)
    if st != 200:
        return None
    out = {"url": url, "tax": {}, "staff": {}}
    i = html.find("Kopējie maksājumi valsts kopbudžetā")
    if i >= 0:
        seg = html[max(0, i - 800): i + 2500]
        years = re.findall(r'<th class="text-right">\s*(20\d\d)\s*</th>', seg)
        def row(label):
            m = re.search(re.escape(label) + r".*?</t[hd]>(.*?)</tr>", seg, re.S)
            if not m:
                return []
            return [re.sub(r"<[^>]+>", "", x).replace("\xa0", "").replace(" ", "").strip()
                    for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", m.group(1), re.S)]
        for y, v in zip(years, row("Kopējie maksājumi valsts kopbudžetā")):
            n = _num(v)
            if n is not None:
                out["tax"][y] = n
        for y, v in zip(years, row("Vidējais darbinieku skaits")):
            n = _num(v)
            if n is not None:
                out["staff"][y] = n
    w = re.search(r'<a data-type="Www" href="([^"]+)"', html)
    if w:
        out["website"] = w.group(1)
    ph = re.search(r'<a data-type="Phone" href="tel:([^"]+)"', html)
    if ph:
        out["phone"] = ph.group(1)
    t = _h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))
    z = re.search(r"Nozare no zl\.lv (.+?) Nozare no zl\.lv", t)
    if z:
        out["zl_category"] = z.group(1).strip()[:80]
    return out


def finance(p, companies, delay=1.2):
    nace = _nace(p)
    n = 0
    for c in companies:
        reg = c.get("reg_no")
        if not reg:
            continue
        fin = c.setdefault("fin", {})
        for y, v in nace.get(reg, {}).items():
            if v["tax"] is not None:
                fin.setdefault("tax", {})[y] = v["tax"]
            if v["staff"] is not None:
                fin.setdefault("staff", {})[y] = v["staff"]
        if fin.get("src_firmas"):
            continue
        f = firmas(reg)
        if f:
            fin.setdefault("tax", {}).update(f["tax"])
            fin.setdefault("staff", {}).update(f["staff"])
            fin["src_firmas"] = f["url"]
            if f.get("website") and not c.get("website"):
                c["website"] = "https://" + domain_of(f["website"])
                c.setdefault("sources", []).append("firmas.lv")
            if f.get("phone"):
                c.setdefault("registry_phone", f["phone"])
            if f.get("zl_category"):
                c["zl_category"] = f["zl_category"]
        n += 1
        if n % 10 == 0:
            print(f"  money data {n}/{len(companies)}", flush=True)
            p.save()
        time.sleep(delay)
    p.log("finance", f"taxes/staff for {n} companies (VID open data + firmas.lv)")


def people(p, companies):
    want = {c["reg_no"]: c for c in companies if c.get("reg_no")}
    roles = {"CHAIR_OF_BOARD": "Chair of the board", "BOARD_MEMBER": "Board member", "": "Board member"}
    added = 0
    with open(_file(p, "officers"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            c = want.get(r["at_legal_entity_registration_number"])
            if not c or r["entity_type"] != "NATURAL_PERSON":
                continue
            parts = r["name"].split()
            name = " ".join(parts[1:] + parts[:1]) if len(parts) >= 2 else r["name"]   # "Surname First" -> "First Surname"
            role = roles.get(r.get("position") or "", (r.get("position") or "").replace("_", " ").title())
            if r.get("governing_body") == "SUPERVISORY_BOARD":
                role = "Supervisory board"
            if _add_person(p, c, name, role, "registry (board)"):
                added += 1
    return added


def _add_person(p, c, name, role, source):
    for x in p.people:
        if x["company_id"] == c["id"] and x["name"].lower() == name.lower():
            return False
    p.people.append({"company_id": c["id"], "name": name, "role": role, "email": "", "email_type": "",
                     "source": source, "linkedin": ""})
    return True


# ------------------------------------------------------------ directories

def directories(p, max_pages=40, delay=0.8):
    """zl.lv category pages (profile: countries.LV.zl_categories, e.g. ["reklamas-suveniri"])."""
    cats = p.cp.get("zl_categories", [])
    found = 0
    for cat in cats:
        seen = set()
        for page in range(1, max_pages + 1):
            st, html, _ = http_get(f"https://www.zl.lv/lv/kategorija/{cat}/?p={page}", timeout=25)
            links = [l for l in dict.fromkeys(re.findall(r'href="(https://www\.zl\.lv/lv/uznemums/[^"/?#]+/)"', html or ""))]
            new = [l for l in links if l not in seen]
            if not new:
                break
            seen.update(new)
            time.sleep(delay)
        for url in sorted(seen):
            st, html, _ = http_get(url, timeout=25)
            if st != 200:
                continue
            t = _h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html))))
            reg = re.search(r"Reģistrācijas numurs (\d{11})", t)
            title = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
            site = re.search(r'href="(https?://(?!www\.zl\.lv|[a-z0-9]+\.zl\.lv|www\.firmas|www\.facebook|youtu|www\.google|fonts|cdn)[^"?]+)\?utm_source=zl\.lv&(?:amp;)?utm_medium=infopage-head', html)
            mail = re.search(r"E-pasts ([\w.+-]+@[\w-]+\.[\w.]+)", t)
            rec = {"brand": _h.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else "",
                   "reg_no": reg.group(1) if reg else "", "website": ("https://" + domain_of(site.group(1))) if site else "",
                   "found_by": f"zl.lv category {cat}"}
            if rec["brand"] or rec["reg_no"]:
                c, created = p.upsert({k: v for k, v in rec.items() if v}, "directory")
                if mail:
                    c.setdefault("directory_emails", [])
                    if mail.group(1) not in c["directory_emails"]:
                        c["directory_emails"].append(mail.group(1))
                found += 1
            time.sleep(delay)
        p.save()
    p.log("directories", f"{found} company pages read from zl.lv ({', '.join(cats)})")
