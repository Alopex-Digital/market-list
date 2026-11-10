"""Fallback for countries without a built-in registry module.

No bulk registry sweep: companies come from web search, directories and Clay company search
(see reference/countries.md for each country's registry search page, used to check single companies).
"""
INFO = {
    "name": "", "language": "", "registry": "see reference/countries.md",
    "money_column": "Revenue {year} (thousand €)",
    "money_note": "No free bulk registry data for this country: money figures only where Claude finds them.",
}

def sweep(p):
    p.log("registry", "no built-in registry for this country - use web search, directories and Clay")

def lookup(p, companies):
    return 0

def finance(p, companies, **kw):
    p.log("finance", "no free money data source built in for this country")

def people(p, companies):
    return 0
