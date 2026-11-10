"""Excel export: 4 tabs.

1 Companies         - the main list (10 columns, same order as the reference list format)
2 Generic contacts  - company, reg. no, website, generic email, phone
3 People            - named people, role, email and where it came from
4 How it was searched
"""
import time
from core import domain_of
import countries

HEAD_FILL = "1F3B4D"
ALT_FILL = "F3F6F8"


def _years(cs, key):
    """The latest year most companies report, then the years before it."""
    from collections import Counter
    latest = Counter()
    for c in cs:
        ys = [y for y, v in ((c.get("fin") or {}).get(key) or {}).items() if v is not None]
        if ys:
            latest[max(ys)] += 1
    if not latest:
        return []
    top = int(latest.most_common(1)[0][0])
    return [str(top - i) for i in range(5)]


def _fmt_num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    except (TypeError, ValueError):
        return v


def export_xlsx(p, out, only_new=False, include_unsure=True):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    keep = ("in", "unsure") if include_unsure else ("in",)
    cs = [c for c in p.companies if (c.get("review") or {}).get("decision") in keep]
    if only_new:
        cs = [c for c in cs if not c.get("existing")]
    cs.sort(key=lambda c: ((c.get("review") or {}).get("decision") != "in", "closed" in (c.get("status") or ""),
                           (c.get("brand") or c.get("legal_name") or "").lower()))
    mod = countries.load(p.country)
    info = mod.INFO
    prof = p.profile
    proof = prof.get("proof", {})
    proof_label = proof.get("label") or "Proof found"

    staff_years = _years(cs, "staff")[:2]
    while len(staff_years) < 2:
        staff_years.append(str(int(staff_years[-1]) - 1) if staff_years else time.strftime("%Y"))
    money_key = "tax" if "Taxes" in info.get("money_column", "") else "revenue"
    money_years = _years(cs, money_key)
    money_year = money_years[0] if money_years else str(int(time.strftime("%Y")) - 1)
    money_head = info.get("money_column", "Revenue {year} (thousand €)").format(year=money_year)

    wb = openpyxl.Workbook()
    thin = Side(style="thin", color="D9DEE3")
    def style_sheet(ws, widths, wrap_cols=()):
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=HEAD_FILL)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 32
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        for r_i, row in enumerate(ws.iter_rows(min_row=2), 2):
            for cell in row:
                cell.border = Border(bottom=thin)
                cell.alignment = Alignment(vertical="top", wrap_text=cell.column in wrap_cols)
                if r_i % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor=ALT_FILL)

    # ---- 1 Companies
    ws = wb.active
    ws.title = "Companies"
    ws.append(["Brand", "Website", "Legal name", "Reg. no", proof_label, f"Employees {staff_years[0]}",
               f"Employees {staff_years[1]}", money_head, "Status", "Note"])
    for c in cs:
        fin = c.get("fin") or {}
        sc = c.get("scan") or {}
        if proof.get("enabled") or sc.get("proof") is not None:
            if not c.get("website"):
                pf = "no website"
            elif not sc.get("ok"):
                pf = "site not reachable"
            else:
                pf = ", ".join(sorted((sc.get("proof") or {}).keys())) or "not identified"
        else:
            pf = "not checked"
        rv = c.get("review") or {}
        note = []
        if c.get("city"):
            note.append(c["city"].title() if c["city"].isupper() else c["city"])
        if rv.get("kind"):
            note.append(rv["kind"])
        if rv.get("note") and rv["note"] not in note:
            note.append(rv["note"])
        if c.get("foreign"):
            note.append(f"foreign seller ({c['foreign']})")
        if rv.get("decision") == "unsure":
            note.append("UNSURE - check")
        if not c.get("website"):
            note.append("no website found")
        mv = (fin.get(money_key) or {})
        if mv.get(money_year) is None:
            older = sorted((y for y in mv if y < money_year and mv[y] is not None), reverse=True)
            if older:
                note.append(f"{money_key.replace('tax', 'taxes')} {older[0]}: {_fmt_num(mv[older[0]])} k€")
        st_ = fin.get("staff") or {}
        if st_.get(staff_years[0]) is None and st_.get(staff_years[1]) is None:
            older = sorted((y for y in st_ if y < staff_years[1] and st_[y] is not None), reverse=True)
            if older:
                note.append(f"staff {older[0]}: {_fmt_num(st_[older[0]])}")
        status = c.get("status") or ("active" if c.get("reg_no") else "registry entry not found")
        ws.append([c.get("brand") or c.get("legal_name"), c.get("website") or "", c.get("legal_name") or "",
                   c.get("reg_no") or "", pf,
                   _fmt_num((fin.get("staff") or {}).get(staff_years[0])), _fmt_num((fin.get("staff") or {}).get(staff_years[1])),
                   _fmt_num((fin.get(money_key) or {}).get(money_year)), status, ". ".join(x.strip().rstrip(".") for x in note if x and x.strip())])
        cell = ws.cell(row=ws.max_row, column=2)
        if cell.value:
            cell.hyperlink = cell.value
            cell.font = Font(color="1F5FAD", underline="single")
    style_sheet(ws, [26, 30, 34, 14, 18, 11, 11, 14, 16, 60], wrap_cols=(3, 10))
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=8):
        for cell in row:
            cell.number_format = "#,##0.##"

    # ---- 2 Generic contacts
    ws2 = wb.create_sheet("Generic contacts")
    ws2.append(["Company name", "Reg. no", "Website", "Generic email", "Phone"])
    for c in cs:
        ct = c.get("contacts") or {}
        ws2.append([c.get("brand") or c.get("legal_name"), c.get("reg_no") or "", c.get("website") or "",
                    ", ".join(ct.get("generic") or []), ", ".join(ct.get("phones") or [])])
    style_sheet(ws2, [30, 14, 30, 40, 26], wrap_cols=(4, 5))

    # ---- 3 People
    ws3 = wb.create_sheet("People")
    ws3.append(["Company", "Reg. no", "Name", "Role", "Email", "Email type", "Source", "LinkedIn"])
    ids = {c["id"]: c for c in cs}
    people = [x for x in p.people if x["company_id"] in ids]
    people.sort(key=lambda x: ((ids[x["company_id"]].get("brand") or "").lower(), not x.get("email"), x["name"]))
    for x in people:
        c = ids[x["company_id"]]
        ws3.append([c.get("brand") or c.get("legal_name"), c.get("reg_no") or "", x["name"], x.get("role", ""),
                    x.get("email", ""), x.get("email_type", ""), x.get("source", ""), x.get("linkedin", "")])
    style_sheet(ws3, [28, 14, 24, 26, 34, 18, 16, 40])

    # ---- 4 How it was searched
    ws4 = wb.create_sheet("How it was searched")
    cp = p.cp
    srcs = {}
    for c in cs:
        for s in c.get("sources", []):
            srcs[s] = srcs.get(s, 0) + 1
    n_in = sum(1 for c in cs if (c.get("review") or {}).get("decision") == "in")
    n_un = len(cs) - n_in
    ex = p.meta.get("existing")
    rows = [
        (f"{info.get('name') or p.country}: {prof.get('name')}", f"built {time.strftime('%d %b %Y')} with the market-list skill"),
        ("Who counts", prof.get("description", "")),
        ("Included", "; ".join(prof.get("include", []))),
        ("Excluded", "; ".join(prof.get("exclude", []))),
        ("Registry", info.get("registry", "")),
        ("Name keywords (registry)", ", ".join(cp.get("name_keywords", []))),
        ("Industry codes", ", ".join(map(str, cp.get("industry_codes", []))) or "-"),
        ("Web search phrases", "; ".join(cp.get("search_queries", []))),
        ("Directories", "; ".join(cp.get("directories", [])) or "-"),
        ("Where companies came from", ", ".join(f"{k}: {v}" for k, v in sorted(srcs.items(), key=lambda x: -x[1]))),
        ("Website check", "Every website was opened by a script (home + contact/about pages); keyword hits decided what Claude reviewed."),
        (proof_label, ("Signals: " + "; ".join(f"{s['name']}: {', '.join(s.get('patterns', []))}" for s in proof.get("signals", [])) +
                       ". 'not identified' only means no proof on the website.") if proof.get("signals") else "not checked"),
        ("Employees", "Average staff from registry/tax data. 0-1 usually means an owner-run company."),
        (money_head, info.get("money_note", "")),
        ("Contacts", "Generic emails and phones from the company website (and registry). People from registry board lists, "
                     "named emails on websites and Clay people search. 'guessed - verify' = built from the company's own email pattern, not checked."),
        ("Result", f"{len(cs)} companies: {n_in} in, {n_un} unsure (marked in the note)" + ("; showing only companies not in your list" if only_new else "")),
    ]
    if ex:
        rows.append(("Your existing list", f"{ex['file']}: {ex['rows']} rows; {ex['matched']} of them were found again by this search"))
    ws4.append(["Item", "Details"])
    for r in rows:
        ws4.append(list(r))
    style_sheet(ws4, [30, 120], wrap_cols=(2,))
    ws4.freeze_panes = None
    ws4.auto_filter.ref = None
    wb.save(out)
    return len(cs)
