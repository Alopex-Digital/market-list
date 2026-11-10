# Countries: what free data exists

Checked November 2026. "Built in" = the engine has a country module (registry sweep, money data,
board members). Every other country works through web search, directories and Clay; use the
registry link to check single companies (status, registry number) by hand or with WebFetch.

## Built in

| Country | Registry sweep | Staff | Money column | Board members | Directory reader |
|---|---|---|---|---|---|
| Finland (FI) | PRH/YTJ full daily file (no key) | Asiakastieto public page | Revenue (Asiakastieto); corporate tax (Vero CSV) | – | – (finder.fi/fonecta.fi via web search) |
| Latvia (LV) | Uzņēmumu reģistrs open data + VID industry codes | VID open data, firmas.lv | Taxes paid (VID open data, firmas.lv) | officers.csv | zl.lv categories |

## Good free data, module not built yet (ask to add one)

| Country | Source | Notes |
|---|---|---|
| Estonia | avaandmed.ariregister.rik.ee (bulk) + EMTA tax files | industry code, staff, revenue, taxes, board – best in the Baltics |
| Norway | data.brreg.no (API, no key) | industry code, exact staff, accounts register with financials |
| Czechia | ares.gov.cz (API, no key) | CZ-NACE filter (5-digit), staff band in RES |
| France | recherche-entreprises.api.gouv.fr (no key) | NAF filter, staff band, some revenue |
| Romania | webservicesp.anaf.ro/bilant (per company) + data.gov.ro bulk | CAEN code, revenue, profit, staff |
| Lithuania | get.data.gov.lt (JAR, balance and P&L datasets) | board members included; staff data site blocks scripts |
| Slovakia | RPO API (rate-limited) + registeruz.sk (financial statements) | |
| UK | Companies House free monthly bulk file (SIC codes) | API key (free) for accounts |
| Ireland | opendata.cro.ie (companies + financial statements datasets) | |
| Poland | KRS API (by number), VAT whitelist | industry codes need a free GUS key |
| Switzerland | zefix.ch (name search, purpose text) | |

## Free after a sign-up (the user registers; the skill then uses their key)

Sweden (Bolagsverket "värdefulla datamängder" API: industry codes + annual reports),
Denmark (CVR system-to-system access, ~3 weeks approval: everything incl. staff and accounts),
Belgium (KBO open data login; NBB annual accounts), Croatia (sudreg-data.gov.hr),
Greece (GEMI open data key). Netherlands: KVK API is paid (about €6/month + €0.02 per lookup);
the free dataset has no company names. Austria: free since 2025 but sign-up needs an Austrian e-ID;
use the WKO "Firmen A–Z" directory instead.

## Web search, directories and Clay only

Germany (handelsregister.de: free search page, 60 lookups an hour, no industry codes, bulk use not
allowed), Italy, Portugal, Spain (BORME daily gazette only), Hungary (search needs a Hungarian login),
Luxembourg, Malta, Cyprus, Bulgaria, Serbia, Ukraine, Moldova, Iceland, Albania, Bosnia and
Herzegovina, Montenegro, North Macedonia, Liechtenstein, Monaco, Andorra, San Marino, Vatican City.

Everywhere: GLEIF (api.gleif.org, free) covers companies that have an LEI code.

## Directories worth searching (with WebSearch allowed_domains)

Finland: finder.fi, fonecta.fi (industry categories, e.g. "Mainoslahjat, liikelahjat").
Latvia: zl.lv (read directly by `directories`), 1188.lv, viss.lv, firmas.lv.
Estonia: inforegister.ee, teatmik.ee. Lithuania: rekvizitai.vz.lt. Sweden: allabolag.se, hitta.se.
Germany: wlw.de, gelbeseiten.de. Poland: panoramafirm.pl, aleo.com. Denmark: proff.dk, krak.dk.
