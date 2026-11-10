"""Finland.

Registry:   PRH / YTJ open data, full daily file (all valid companies), no key.
Money:      Asiakastieto public company page (revenue + staff, last 5 years), one page per company.
            Vero corporate income tax CSV (yearly, published every November).
People:     not in free registry data -> websites + Clay.
"""
import os, re, json, zipfile, csv, time, html as _h
from core import download, http_get, norm_name, domain_of, name_matches, strip_accents

INFO = {
    "name": "Finland", "language": "Finnish (also Swedish)",
    "registry": "PRH / YTJ open data (avoindata.prh.fi)",
    "money_column": "Revenue {year} (thousand €)",
    "money_note": "Revenue and staff from Asiakastieto's public page; corporate income tax from Vero open data.",
}

BULK_URL = "https://avoindata.prh.fi/opendata-ytj-api/v3/all_companies"
VERO_PAGE = "https://www.vero.fi/avoindata"
SITUATION = {"KONK": "bankruptcy", "SELTILA": "liquidation", "SANE": "restructuring"}


def _index_path(p):
    return os.path.join(p.cache, "fi_index.jsonl")


def build_index(p):
    """Stream the 1.5 GB JSON once into a small line-per-company index."""
    idx = _index_path(p)
    if os.path.exists(idx) and time.time() - os.path.getmtime(idx) < 6 * 86400:
        return idx
    z = download(BULK_URL, os.path.join(p.cache, "fi_all_companies.zip"), min_age_hours=144)
    print("  indexing Finnish registry (one-off, a few minutes) ...", flush=True)
    zf = zipfile.ZipFile(z)
    f = zf.open(zf.infolist()[0])
    dec = json.JSONDecoder()
    buf = ""
    f.read(1)
    n = 0
    with open(idx + ".part", "w", encoding="utf-8") as out:
        while True:
            chunk = f.read(4 << 20)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "ignore")
            pos = 0
            L = len(buf)
            while True:
                while pos < L and buf[pos] in ", \n\r\t]":
                    pos += 1
                if pos >= L:
                    break
                try:
                    o, end = dec.raw_decode(buf, pos)
                except ValueError:
                    break
                pos = end
                n += 1
                forms = o.get("companyForms") or []
                form = ""
                for fm in forms:
                    for d in fm.get("descriptions") or []:
                        if d.get("languageCode") == "3":
                            form = d.get("description", "")
                if "Housing" in form:      # skip housing companies (asunto-oy), 200k+ of them
                    continue
                cur = [x for x in (o.get("names") or []) if not x.get("endDate")]
                names = [x["name"] for x in cur if x.get("type") != "3"]   # official / parallel names
                aux = [x["name"] for x in cur if x.get("type") == "3"]     # auxiliary trade names (aputoiminimi)
                mbl = (o.get("mainBusinessLine") or {})
                city = ""
                for a in o.get("addresses") or []:
                    for po in a.get("postOffices") or []:
                        if po.get("languageCode") == "1":
                            city = po.get("city", "").title()
                            break
                    if city:
                        break
                sit = [SITUATION.get(s.get("type"), s.get("type")) for s in (o.get("companySituations") or []) if not s.get("endDate")]
                rec = {"id": o["businessId"]["value"], "n": names, "a": aux, "c": mbl.get("type", ""),
                       "w": ((o.get("website") or {}).get("url") or ""), "city": city, "form": form,
                       "st": o.get("status"), "sit": sit, "reg": (o["businessId"].get("registrationDate") or "")}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            buf = buf[pos:]
    os.replace(idx + ".part", idx)
    print(f"  indexed {n:,} records", flush=True)
    return idx


def _iter(p):
    with open(build_index(p), encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def _status(r):
    if r.get("sit"):
        return "closing (" + ", ".join(r["sit"]) + ")"
    return "active" if r.get("st") == "2" else "inactive"


def _record(r, why, kws=()):
    names = r["n"] + r["a"]
    # brand = the trade name that matched a keyword; otherwise the official name
    brand = next((a for a in r["a"] if name_matches(a, kws)), "") or (r["n"][0] if r["n"] else "")
    return {"legal_name": r["n"][0] if r["n"] else "", "brand": brand, "reg_no": r["id"],
            "website": ("https://" + domain_of(r["w"])) if r["w"] else "", "city": r["city"],
            "industry_code": r["c"], "status": _status(r), "aliases": names,
            "registry_match": why}


def sweep(p):
    cp = p.cp
    kws = cp.get("name_keywords", [])
    weak = cp.get("name_keywords_weak", [])
    codes = [str(c).replace(".", "") for c in cp.get("industry_codes", [])]
    neg = cp.get("name_exclude", [])
    added = 0
    with_code_no_site = 0
    for r in _iter(p):
        names = r["n"] + r["a"]
        hit = None
        for nm in names:
            hit = name_matches(nm, kws)
            if hit:
                break
        if hit and any(name_matches(nm, neg) for nm in names):
            hit = None
        weak_hit = None
        if not hit and weak:
            for nm in names:
                weak_hit = name_matches(nm, weak)
                if weak_hit:
                    break
        code_hit = codes and any(r["c"].startswith(c) for c in codes)
        if hit:
            p.upsert(_record(r, f"name contains '{hit}'", kws + weak), "registry-name")
            added += 1
        elif weak_hit and (r["w"] or code_hit):
            p.upsert(_record(r, f"name contains '{weak_hit}' (weak word, website must confirm)", kws + weak), "registry-weak")
            added += 1
        elif code_hit:
            if r["w"]:
                p.upsert(_record(r, f"industry code {r['c']} + website"), "registry-industry")
                added += 1
            else:
                with_code_no_site += 1
    p.log("registry", f"{added} candidates from the Finnish registry; {with_code_no_site} more had the industry code but no website (skipped)")


def lookup(p, companies):
    """Find registry data for companies found on the web (by name or website)."""
    want_dom = {domain_of(c["website"]): c for c in companies if c.get("website")}
    want_name = {}
    for c in companies:
        for nm in [c.get("brand"), c.get("legal_name")] + c.get("aliases", []):
            n = norm_name(nm)
            if n and len(n) > 2:
                want_name.setdefault(n, []).append(c)
    hits = 0
    for r in _iter(p):
        c = None
        if r["w"] and domain_of(r["w"]) in want_dom:
            c = want_dom[domain_of(r["w"])]
        else:
            for nm in r["n"] + r["a"]:
                lst = want_name.get(norm_name(nm))
                if lst:
                    c = lst[0]
                    break
        if c is not None and not c.get("reg_no"):
            rec = _record(r, "matched by " + ("website" if r["w"] and domain_of(r["w"]) in want_dom else "name"))
            for k, v in rec.items():
                if v and not c.get(k):
                    c[k] = v
            hits += 1
    return hits


# ------------------------------------------------------------ money

def _vero_file(p):
    st, page, _ = http_get(VERO_PAGE, timeout=30)
    links = re.findall(r'href="([^"]+\.csv)"', page)
    best = None
    for l in links:
        m = re.search(r"(20\d\d)", l)
        if m and "muutos" not in l:
            y = int(m.group(1))
            if not best or y > best[0]:
                best = (y, l)
    if not best:
        return None, None
    url = best[1] if best[1].startswith("http") else "https://www.vero.fi" + best[1]
    path = os.path.join(p.cache, f"fi_vero_{best[0]}.csv")
    download(url, path, min_age_hours=24 * 30)
    return best[0], path


def _num(s):
    s = (s or "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def asiakastieto(reg_no):
    """Revenue (k€) and staff by year from the public Asiakastieto page (its key-figures table)."""
    digits = reg_no.replace("-", "")
    st, html, url = http_get(f"https://www.asiakastieto.fi/yritykset/fi/x/{digits}/taloustiedot", timeout=25)
    if st != 200 or not html:
        return None
    out = {"url": url, "revenue": {}, "staff": {}}
    i = html.find("financial-information--ratios--header")
    if i < 0:
        return out
    seg = html[i - 200: i + 6000]
    years = re.findall(r"ratios--header\">\s*\d{1,2}\s*/\s*(20\d\d)\s*<", seg)
    for label, key in (("Liikevaihto (1000", "revenue"), ("Henkilöstö", "staff")):
        m = re.search(r"<td>\s*" + re.escape(label) + r".*?</td>(.*?)</tr>", seg, re.S)
        if not m:
            continue
        cells = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        for y, v in zip(years, cells):
            n = _num(v)
            if n is not None:
                out[key][y] = n
    return out


def finance(p, companies, delay=1.5, threads=2):
    from concurrent.futures import ThreadPoolExecutor
    year, vpath = _vero_file(p)
    tax = {}
    if vpath:
        want = {c["reg_no"] for c in companies if c.get("reg_no")}
        with open(vpath, encoding="latin-1") as f:
            r = csv.reader(f, delimiter=";")
            next(r)
            for row in r:
                if len(row) > 5 and row[1] in want:
                    tax[row[1]] = _num(row[5])
    todo = []
    for c in companies:
        if not c.get("reg_no"):
            continue
        fin = c.setdefault("fin", {})
        if c["reg_no"] in tax and tax[c["reg_no"]] is not None:
            fin.setdefault("corp_tax", {})[str(year)] = round(tax[c["reg_no"]] / 1000, 2)
        if not fin.get("src_at"):
            todo.append(c)

    def one(c):
        a = asiakastieto(c["reg_no"])
        if a is None:                 # throttled or timed out: wait and try once more
            time.sleep(8)
            a = asiakastieto(c["reg_no"])
        time.sleep(delay)
        return c, a

    n = 0
    with ThreadPoolExecutor(max_workers=threads) as ex:
        for c, a in ex.map(one, todo):
            fin = c["fin"]
            if a:
                fin["revenue"] = a.get("revenue", {})
                fin["staff"] = a.get("staff", {})
                fin["src_at"] = a.get("url")
            n += 1
            if n % 20 == 0:
                print(f"  money data {n}/{len(todo)}", flush=True)
                p.save()
    p.log("finance", f"revenue/staff for {n} companies (Asiakastieto); corporate tax year {year} (Vero)")


def people(p, companies):
    return 0   # Finnish open data has no board members; websites + Clay cover people.
