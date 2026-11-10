#!/usr/bin/env python3
"""market-list engine: build a complete list of one kind of company in one country.

Every command reads and writes the project folder, so you can stop at any time and
run `status` to see where you are. Typical order:

  new -> registry -> add (web/directory finds) -> lookup -> guess-sites -> scan -> screen
      -> review/decide -> finance -> contacts -> (people-todo/people-add with Clay) -> existing -> export
"""
import argparse, csv, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import Project, new_project, load_json, save_json, domain_of, norm_name, http_get, strip_accents
import countries

HERE = os.path.dirname(os.path.abspath(__file__))


READ_ONLY = {"status", "review", "needs-site", "people-todo"}


def P(args):
    return Project(args.project, write=args.cmd not in READ_ONLY)


# ------------------------------------------------------------------ setup / status

def cmd_doctor(a):
    ok = True
    print(f"python {sys.version.split()[0]}", "OK" if sys.version_info >= (3, 8) else "TOO OLD (need 3.8+)")
    try:
        import openpyxl  # noqa
        print("openpyxl OK")
    except ImportError:
        ok = False
        print("openpyxl MISSING -> run: python3 -m pip install --user openpyxl")
    st, _, _ = http_get("https://data.brreg.no/enhetsregisteret/api/enheter?size=1", timeout=15)
    print("internet", "OK" if st == 200 else f"PROBLEM (status {st})")
    ok = ok and st == 200
    import shutil
    free = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    print(f"free disk {free:.1f} GB", "OK" if free > 3 else "LOW (registry files need up to ~2 GB)")
    if not shutil.which("npx"):
        ok = False
        print("Node.js/npx MISSING -> needed for the Clay bridge; install Node.js from nodejs.org")
    elif a.clay:
        try:
            from clay import Clay
            c = Clay(timeout=180)
            ws = c.call("get-current-workspace", {})
            c.close()
            print("Clay OK:", (ws or {}).get("workspaceName") or ws)
        except Exception as e:
            ok = False
            print("Clay PROBLEM:", str(e)[:200], "-> see reference/clay.md")
    else:
        print("npx OK (add --clay to test the Clay login)")
    print("ALL GOOD" if ok else "FIX THE ITEMS ABOVE")


def cmd_new(a):
    prof = load_json(a.profile, None)
    if prof is None:
        sys.exit(f"profile not found: {a.profile}")
    folder = new_project(a.project, a.country, prof)
    print(f"project created: {folder}")


def cmd_status(a):
    p = P(a)
    cs = p.companies
    def cnt(f):
        return sum(1 for c in cs if f(c))
    print(f"Project {p.dir}  country {p.country}  profile '{p.profile.get('name')}'")
    print(f"companies: {len(cs)}")
    print(f"  with website: {cnt(lambda c: c.get('website'))}   with reg no: {cnt(lambda c: c.get('reg_no'))}")
    print(f"  scanned: {cnt(lambda c: c.get('scan'))}   site reachable: {cnt(lambda c: (c.get('scan') or {}).get('ok'))}")
    for d in ("in", "unsure", "out", None):
        print(f"  decision {d or 'pending'}: {cnt(lambda c, d=d: (c.get('review') or {}).get('decision') == d)}")
    print(f"  money data: {cnt(lambda c: c.get('fin'))}   existing-list matches: {cnt(lambda c: c.get('existing'))}")
    print(f"people: {len(p.people)}   with email: {sum(1 for x in p.people if x.get('email'))}")
    print("stages done:", ", ".join(f"{k} ({v})" for k, v in p.meta.get("stages", {}).items()) or "none")
    print("next:", suggest_next(p))


def suggest_next(p):
    s = p.meta.get("stages", {})
    cs = p.companies
    order = ["registry", "web", "lookup", "guess-sites", "scan", "screen", "review", "finance", "contacts", "people", "export"]
    for st in order:
        if st == "web" and "web" not in s:
            return "web search + directories (Claude), then `add`"
        if st == "review":
            pend = [c for c in cs if (c.get("review") or {}).get("decision") is None]
            if pend:
                return f"`review` ({len(pend)} companies waiting)"
            continue
        if st not in s:
            return f"`{st}`"
    return "done - run `export` again after any change"


# ------------------------------------------------------------------ discovery

def cmd_registry(a):
    p = P(a)
    countries.load(p.country).sweep(p)
    p.save()


def read_rows(path):
    if path.endswith(".json"):
        return load_json(path, [])
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def cmd_directories(a):
    p = P(a)
    mod = countries.load(p.country)
    if not hasattr(mod, "directories"):
        print("no built-in directory reader for this country - use web search with the directory's site name")
        return
    mod.directories(p)
    p.save()


def cmd_add(a):
    """Add companies found by web search, directories, Clay or by hand. Columns: brand, website,
    legal_name, reg_no, city, note (any may be empty, but brand or website is needed)."""
    p = P(a)
    new = merged = 0
    for r in read_rows(a.file):
        r = {k: (v or "").strip() if isinstance(v, str) else v for k, v in r.items()}
        if not (r.get("brand") or r.get("website") or r.get("legal_name")):
            continue
        if r.get("website"):
            r["website"] = "https://" + domain_of(r["website"])
        rec = {k: r.get(k) for k in ("brand", "website", "legal_name", "reg_no", "city", "note") if r.get(k)}
        if r.get("found_by"):
            rec["found_by"] = r["found_by"]
        _, created = p.upsert(rec, a.source)
        new += created
        merged += (not created)
    p.meta.setdefault("stages", {})["web"] = time.strftime("%Y-%m-%d %H:%M")
    p.log("add", f"{new} new + {merged} already known, source '{a.source}'")
    p.save()


def cmd_lookup(a):
    p = P(a)
    todo = [c for c in p.companies if not c.get("reg_no")]
    hits = countries.load(p.country).lookup(p, todo) if todo else 0
    p.log("lookup", f"registry data found for {hits} of {len(todo)} companies that had none")
    p.save()


def slug_variants(name):
    n = norm_name(name)
    if not n:
        return []
    words = n.split()
    out = ["".join(words), "-".join(words)]
    if len(words) > 1:
        out.append(words[0])
    return [o for o in dict.fromkeys(out) if len(o) >= 3]


def cmd_guess_sites(a):
    """Try company-name domains (name.fi, name.lv ...) for candidates without a website, and accept a
    domain only when the page mentions the company name. A DNS check skips domains that do not exist."""
    import socket
    from concurrent.futures import ThreadPoolExecutor, as_completed
    p = P(a)
    tlds = [p.country.lower(), "com", "eu"]
    todo = [c for c in p.companies if not c.get("website") and not c.get("site_guessed")
            and (c.get("review") or {}).get("decision") != "out"]

    def exists(d):
        try:
            socket.setdefaulttimeout(4)
            socket.gethostbyname(d)
            return True
        except Exception:
            return False

    def one(c):
        names = [c.get("brand"), c.get("legal_name")] + c.get("aliases", [])[:3]
        tokens = [t for t in norm_name(c.get("brand") or c.get("legal_name")).split() if len(t) > 2]
        tried = set()
        for nm in names:
            for s in slug_variants(nm):
                for tld in tlds:
                    d = f"{s}.{tld}"
                    if d in tried:
                        continue
                    tried.add(d)
                    if not exists(d):
                        continue
                    st, html, final = http_get(f"https://{d}", timeout=8, retries=0)
                    if not (st and st < 400 and html):
                        st, html, final = http_get(f"http://{d}", timeout=8, retries=0)
                    if st and st < 400 and html:
                        low = strip_accents(html.lower())
                        if tokens and all(t in low for t in tokens[:2]) or (c.get("reg_no") and c["reg_no"] in html):
                            return "https://" + domain_of(final)
        return ""

    found = done = 0
    last = time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(one, c): c for c in todo}
        for f in as_completed(futs):
            c = futs[f]
            try:
                site = f.result()
            except Exception:
                site = ""
            c["site_guessed"] = True
            done += 1
            if site:
                c["website"] = site
                c.setdefault("sources", []).append("domain-guess")
                found += 1
            if time.time() - last > 30:
                p.save()
                last = time.time()
                print(f"  {done}/{len(todo)} checked, {found} websites found", flush=True)
    # a guessed domain that matches several companies is a generic word (promo.com), not theirs
    from collections import Counter
    cnt = Counter(domain_of(c["website"]) for c in p.companies if c.get("website"))
    dropped = 0
    for c in p.companies:
        if "domain-guess" in c.get("sources", []) and c.get("website") and cnt[domain_of(c["website"])] > 1:
            c.pop("website"); c.pop("scan", None)
            c["sources"].remove("domain-guess")
            dropped += 1
    p.log("guess-sites", f"found a website for {found - dropped} of {len(todo)} companies by trying name domains"
          + (f" ({dropped} shared generic domains dropped)" if dropped else ""))
    p.save()


def cmd_needs_site(a):
    p = P(a)
    rows = [c for c in p.companies if not c.get("website") and (c.get("review") or {}).get("decision") != "out"]
    for c in rows[: a.limit]:
        print(f"{c['id']} | {c.get('brand') or c.get('legal_name')} | {c.get('legal_name','')} | {c.get('city','')} | {c.get('registry_match','')}")
    print(f"-- {len(rows)} without website. Find them with web search, then: set --id ID --website URL (or --no-site)")


def cmd_set(a):
    p = P(a)
    c = next((x for x in p.companies if x["id"] == a.id), None)
    if not c:
        sys.exit("no such id")
    if a.website:
        c["website"] = "https://" + domain_of(a.website)
        c.pop("scan", None)
    if a.no_site:
        c["no_site"] = True
    for kv in a.field or []:
        k, v = kv.split("=", 1)
        c[k] = v
    p.save()
    print("ok")


# ------------------------------------------------------------------ scanning & screening

def cmd_scan(a):
    from scan import scan_many
    p = P(a)
    prof = p.profile
    proof = prof.get("proof", {})
    use_proof = a.proof or proof.get("enabled")
    todo = [c for c in p.companies if c.get("website") and (a.rescan or not c.get("scan"))
            and (c.get("review") or {}).get("decision") != "out"]
    if a.only_in:
        todo = [c for c in todo if (c.get("review") or {}).get("decision") in ("in", "unsure")]
    todo = todo[: a.limit] if a.limit else todo
    if not todo:
        print("nothing to scan")
        return
    kws = p.cp.get("site_keywords", [])
    t0 = time.time()
    last = [time.time()]
    def progress(done, total):
        if done % 25 == 0 or done == total:
            print(f"  scanned {done}/{total}  ({time.time() - t0:.0f}s)", flush=True)
        if time.time() - last[0] > 30:      # save every 30 s, so a stop loses little
            p.save()
            last[0] = time.time()
    scan_many(todo, kws, proof.get("signals") if use_proof else None, deep_proof=bool(use_proof),
              threads=a.threads, on_done=progress)
    p.log("scan", f"scanned {len(todo)} websites" + (" with proof signals" if use_proof else ""))
    p.save()


def cmd_screen(a):
    """Automatic first sort, so Claude only reviews plausible companies."""
    p = P(a)
    min_hits = p.cp.get("min_site_hits", 2)
    auto_out = pend = 0
    for c in p.companies:
        if (c.get("review") or {}).get("decision"):
            continue
        sc = c.get("scan") or {}
        hits = sum((sc.get("kw") or {}).values())
        srcs = set(c.get("sources", []))
        only_industry = srcs <= {"registry-industry", "registry-weak", "domain-guess", "firmas.lv"}
        if only_industry and sc.get("ok") and hits < min_hits:
            c["review"] = {"decision": "out", "by": "auto", "note": f"website does not mention the topic ({hits} keyword hits)"}
            auto_out += 1
        elif only_industry and not c.get("website"):
            c["review"] = {"decision": "out", "by": "auto", "note": "industry code only, no website to check"}
            auto_out += 1
        elif only_industry and sc and not sc.get("ok"):
            c["review"] = {"decision": "out", "by": "auto", "note": "industry code only, website not reachable"}
            auto_out += 1
        else:
            pend += 1
    p.log("screen", f"auto-excluded {auto_out}; {pend} left for review")
    p.save()


def short(c):
    sc = c.get("scan") or {}
    kw = sc.get("kw") or {}
    top = ", ".join(f"{k}:{v}" for k, v in sorted(kw.items(), key=lambda x: -x[1])[:5])
    txt = (sc.get("title", "") + " | " + (sc.get("description") or sc.get("snippet", "")[:220])).strip(" |")
    site = domain_of(c.get("website")) or ("NO SITE" if not sc else "")
    if sc and not sc.get("ok"):
        site += " (unreachable)"
    proof = ", ".join(f"{k}:{v}" for k, v in (sc.get("proof") or {}).items())
    return (f"{c['id']} | {c.get('brand') or c.get('legal_name')} | legal: {c.get('legal_name','-')} | {c.get('reg_no','-')} | "
            f"{c.get('city','')} | code {c.get('industry_code','-')} | {c.get('status','')} | site: {site} | "
            f"found: {','.join(c.get('sources', []))} | kw: {top or '-'}" + (f" | proof: {proof}" if proof else "") +
            f" | {txt[:300]}")


def cmd_review(a):
    p = P(a)
    pend = [c for c in p.companies if (c.get("review") or {}).get("decision") is None]
    if a.decision:
        pend = [c for c in p.companies if (c.get("review") or {}).get("decision") == a.decision]
    print(f"# {len(pend)} companies; showing {min(a.next, len(pend))}. Decide in/out/unsure, then `decide --file`.")
    for c in pend[: a.next]:
        print(short(c))


def cmd_decide(a):
    """File: JSON list of {id, decision: in|out|unsure, kind, note, brand(optional)}."""
    p = P(a)
    by = {c["id"]: c for c in p.companies}
    n = 0
    for d in load_json(a.file, []):
        c = by.get(d.get("id"))
        if not c:
            print("unknown id", d.get("id"))
            continue
        c["review"] = {"decision": d["decision"], "kind": d.get("kind", ""), "note": d.get("note", ""), "by": "claude"}
        if d.get("brand"):
            c["brand"] = d["brand"]
        if d.get("foreign"):
            c["foreign"] = d["foreign"]
        n += 1
    p.meta.setdefault("stages", {})["review"] = time.strftime("%Y-%m-%d %H:%M")
    left = sum(1 for c in p.companies if (c.get("review") or {}).get("decision") is None)
    p.log("review", f"{n} decisions saved; {left} still waiting")
    p.save()


# ------------------------------------------------------------------ money, contacts

def chosen(p, include_unsure=True):
    keep = ("in", "unsure") if include_unsure else ("in",)
    return [c for c in p.companies if (c.get("review") or {}).get("decision") in keep]


def cmd_finance(a):
    p = P(a)
    cs = chosen(p)
    if a.limit:
        cs = cs[: a.limit]
    countries.load(p.country).finance(p, cs)
    p.save()


def cmd_contacts(a):
    """Emails/phones from the scanned websites + registry board members + pattern guesses."""
    from scan import email_kind, name_from_email
    p = P(a)
    cs = chosen(p)
    mod = countries.load(p.country)
    board = mod.people(p, cs)
    named = generic = guessed = 0
    for c in cs:
        sc = c.get("scan") or {}
        dom = domain_of(c.get("website"))
        gen, phones = [], list(sc.get("phones") or [])
        if c.get("registry_phone") and c["registry_phone"] not in phones:
            phones.append(c["registry_phone"])
        patterns = set()
        for e in list(sc.get("emails") or []) + [x for x in c.get("directory_emails", []) if x not in (sc.get("emails") or [])]:
            kind = email_kind(e)
            own = dom and e.split("@")[1].endswith(dom)
            if kind == "maybe-named" and own:
                # first-name address (harri@company.fi): a person's own mailbox
                first = e.split("@")[0].capitalize()
                if not any(x["company_id"] == c["id"] and x.get("email") == e for x in p.people):
                    p.people.append({"company_id": c["id"], "name": first, "role": "", "email": e,
                                     "email_type": "personal (first-name address)", "source": "website", "linkedin": ""})
                    named += 1
                continue
            if kind == "generic" or (kind in ("other", "maybe-named") and not name_from_email(e)):
                if own or not gen:
                    gen.append(e)
                continue
            nm = name_from_email(e)
            if nm:
                patterns.add("first.last" if "." in e.split("@")[0] else "first-last" if "-" in e.split("@")[0] else "first_last")
                person = next((x for x in p.people if x["company_id"] == c["id"] and norm_name(x["name"]) == norm_name(nm)), None)
                if person:
                    person["email"], person["email_type"] = e, "named (website)"
                else:
                    p.people.append({"company_id": c["id"], "name": nm, "role": "", "email": e, "email_type": "named (website)",
                                     "source": "website", "linkedin": ""})
                named += 1
        c["contacts"] = {"generic": gen[:4], "phones": phones[:4], "pattern": sorted(patterns)}
        generic += bool(gen)
        # guess emails for people without one, only when the company's own pattern is known
        if dom and len(patterns) == 1:
            pat = patterns.pop()
            sep = {"first.last": ".", "first-last": "-", "first_last": "_"}[pat]
            for x in p.people:
                if x["company_id"] == c["id"] and not x.get("email"):
                    parts = strip_accents(x["name"].lower()).split()
                    if len(parts) >= 2:
                        x["email"] = f"{re.sub('[^a-z]', '', parts[0])}{sep}{re.sub('[^a-z]', '', parts[-1])}@{dom}"
                        x["email_type"] = "guessed - verify"
                        guessed += 1
    p.log("contacts", f"{board} board members, {named} named emails, {generic} companies with a generic email, {guessed} guessed emails")
    p.save()


def cmd_people_todo(a):
    """Companies (domains) that still have no named person with an email -> for Clay people search."""
    p = P(a)
    have = {x["company_id"] for x in p.people if x.get("email") and "guessed" not in x.get("email_type", "")}
    done = set(p.meta.get("clay_done", []))
    rows = [c for c in chosen(p, include_unsure=False) if c.get("website") and c["id"] not in have and c["id"] not in done]
    for c in rows[: a.batch]:
        print(f"{c['id']} | {domain_of(c['website'])} | {c.get('brand') or c.get('legal_name')}")
    print(f"-- {len(rows)} companies need people. After Clay search: people-add --file results.json")


def cmd_people_add(a):
    """File: JSON list of {company_id or domain, name, role, linkedin, email}. Marks those companies as searched."""
    p = P(a)
    by_dom = {domain_of(c.get("website")): c for c in p.companies if c.get("website")}
    by_id = {c["id"]: c for c in p.companies}
    added = 0
    done = set(p.meta.get("clay_done", []))
    for r in load_json(a.file, []):
        c = by_id.get(r.get("company_id")) or by_dom.get(domain_of(r.get("domain", "")))
        if not c:
            continue
        done.add(c["id"])
        if not r.get("name"):
            continue
        x = next((y for y in p.people if y["company_id"] == c["id"] and norm_name(y["name"]) == norm_name(r["name"])), None)
        if x is None:
            x = {"company_id": c["id"], "name": r["name"], "role": "", "email": "", "email_type": "", "source": a.source, "linkedin": ""}
            p.people.append(x)
            added += 1
        for k in ("role", "linkedin"):
            if r.get(k) and not x.get(k):
                x[k] = r[k]
        if r.get("email") and (not x.get("email") or "guessed" in x.get("email_type", "")):
            x["email"], x["email_type"] = r["email"], r.get("email_type", f"named ({a.source})")
    for cid in a.searched or []:
        done.add(cid)
    p.meta["clay_done"] = sorted(done)
    p.log("people", f"{added} people added from {a.source}")
    p.save()


def cmd_people_clay(a):
    """Free Clay people search for every 'in' company with a website, 10 domains per call, saved after each call."""
    from clay import Clay, people_for_domains
    p = P(a)
    done = set(p.meta.get("clay_done", []))
    rows = [c for c in chosen(p, include_unsure=a.include_unsure) if c.get("website") and c["id"] not in done]
    if not rows:
        print("nothing left for Clay")
        return
    by_dom = {domain_of(c["website"]): c for c in rows}
    clay = Clay()
    added = 0
    try:
        doms = list(by_dom)
        for i in range(0, len(doms), 10):
            part = doms[i:i + 10]
            try:
                ppl, task = people_for_domains(clay, part)
            except Exception as e:
                print(f"  Clay error on batch {i // 10 + 1}: {str(e)[:120]} - stopping; run again to continue")
                break
            for r in ppl:
                c = by_dom.get(domain_of(r.get("domain") or "")) or by_dom.get(r.get("domain"))
                if not c or not r.get("name"):
                    continue
                if any(x["company_id"] == c["id"] and norm_name(x["name"]) == norm_name(r["name"]) for x in p.people):
                    continue
                p.people.append({"company_id": c["id"], "name": r["name"], "role": r.get("role", ""), "email": "",
                                 "email_type": "", "source": "Clay (LinkedIn)", "linkedin": r.get("linkedin", ""),
                                 "clay_task": task, "clay_entity": r.get("clay_entity")})
                added += 1
            for d in part:
                done.add(by_dom[d]["id"])
            p.meta["clay_done"] = sorted(done)
            p.save()
            print(f"  Clay batch {i // 10 + 1}/{(len(doms) + 9) // 10}: {len(ppl)} people", flush=True)
            time.sleep(1)
    finally:
        clay.close()
    p.log("people", f"{added} people found with Clay people search (free)")
    p.save()


# ------------------------------------------------------------------ existing list, export

def cmd_existing(a):
    """Mark companies that are already in your own list (xlsx/csv), so the export can show only new ones."""
    p = P(a)
    rows = []
    if a.file.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(a.file, data_only=True)
        ws = wb[a.sheet] if a.sheet else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
        rows = [dict(zip(head, r)) for r in it]
    else:
        rows = read_rows(a.file)
    def col(r, *names):
        for n in names:
            for k in r:
                if k and k.lower().startswith(n):
                    return str(r[k] or "").strip()
        return ""
    keys = set()
    for r in rows:
        reg = re.sub(r"\D", "", col(r, "reg", "registry", "business id", "y-tunnus"))
        dom = domain_of(col(r, "website", "web", "url"))
        names = [norm_name(col(r, "brand", "name")), norm_name(col(r, "legal"))]
        for k in [("r", reg), ("d", dom)] + [("n", n) for n in names]:
            if k[1]:
                keys.add(k)
    hit = 0
    for c in p.companies:
        ks = {("r", re.sub(r"\D", "", c.get("reg_no", ""))), ("d", domain_of(c.get("website"))),
              ("n", norm_name(c.get("brand"))), ("n", norm_name(c.get("legal_name")))}
        ks |= {("n", norm_name(x)) for x in c.get("aliases", [])}
        if any(k[1] and k in keys for k in ks):
            c["existing"] = True
            hit += 1
    found_in = sum(1 for c in p.companies if c.get("existing") and (c.get("review") or {}).get("decision") in ("in", "unsure"))
    p.meta["existing"] = {"file": os.path.basename(a.file), "rows": len(rows), "matched": hit, "matched_in": found_in}
    p.log("existing", f"{len(rows)} rows in your list; {hit} of our companies match it ({found_in} of them kept as in/unsure)")
    p.save()


def cmd_export(a):
    from export import export_xlsx
    p = P(a)
    out = a.out or os.path.join(p.dir, f"{p.country}_{re.sub(r'[^A-Za-z0-9]+', '_', p.profile.get('name', 'list'))}_{time.strftime('%Y-%m-%d')}.xlsx")
    n = export_xlsx(p, out, only_new=a.only_new, include_unsure=not a.no_unsure)
    p.log("export", f"{n} companies written to {out}")
    p.save()


# ------------------------------------------------------------------ CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def sp(name, fn, proj=True):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        if proj:
            s.add_argument("--project", required=True)
        return s
    s = sp("doctor", cmd_doctor, proj=False); s.add_argument("--clay", action="store_true")
    s = sp("new", cmd_new); s.add_argument("--country", required=True); s.add_argument("--profile", required=True)
    sp("status", cmd_status)
    sp("registry", cmd_registry)
    sp("directories", cmd_directories)
    s = sp("add", cmd_add); s.add_argument("--file", required=True); s.add_argument("--source", default="web")
    sp("lookup", cmd_lookup)
    sp("guess-sites", cmd_guess_sites)
    s = sp("needs-site", cmd_needs_site); s.add_argument("--limit", type=int, default=40)
    s = sp("set", cmd_set); s.add_argument("--id", required=True); s.add_argument("--website"); s.add_argument("--no-site", action="store_true"); s.add_argument("--field", action="append")
    s = sp("scan", cmd_scan); s.add_argument("--proof", action="store_true"); s.add_argument("--rescan", action="store_true")
    s.add_argument("--limit", type=int, default=0); s.add_argument("--threads", type=int, default=10); s.add_argument("--only-in", action="store_true")
    sp("screen", cmd_screen)
    s = sp("review", cmd_review); s.add_argument("--next", type=int, default=25); s.add_argument("--decision")
    s = sp("decide", cmd_decide); s.add_argument("--file", required=True)
    s = sp("finance", cmd_finance); s.add_argument("--limit", type=int, default=0)
    sp("contacts", cmd_contacts)
    s = sp("people-todo", cmd_people_todo); s.add_argument("--batch", type=int, default=10)
    s = sp("people-add", cmd_people_add); s.add_argument("--file", required=True); s.add_argument("--source", default="clay"); s.add_argument("--searched", nargs="*")
    s = sp("people-clay", cmd_people_clay); s.add_argument("--include-unsure", action="store_true")
    s = sp("existing", cmd_existing); s.add_argument("--file", required=True); s.add_argument("--sheet")
    s = sp("export", cmd_export); s.add_argument("--out"); s.add_argument("--only-new", action="store_true"); s.add_argument("--no-unsure", action="store_true")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
