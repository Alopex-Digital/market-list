# The search profile

A profile describes one niche. Claude writes it from the user's answers; the user never has to
edit it. `profiles/promo-products.json` is a complete example.

```
name              short title, used in file names and the Excel
description       one or two sentences: who counts
include / exclude plain-language rules Claude follows during review (also printed in the Excel)
proof             optional website signals
  enabled         false by default (slower, uses more Claude limits)
  label           Excel column title, e.g. "Suppliers found"
  signals         [{name, patterns (regex, case-insensitive), min_hits}]
countries.<CC>    one block per country code
  name_keywords        strong words: a company whose registry name contains one is a candidate
                       (lower case, no need for endings: "liikelahj" matches liikelahjat, liikelahjapalvelu)
  name_keywords_weak   words that are only a hint ("print", "logo"): candidate only if the website confirms
  name_exclude         words that disqualify a name match
  industry_codes       national industry code prefixes (NACE/TOL/EMTAK...). Companies with these codes
                       are candidates only when their website mentions the topic
  industry_min_staff   (optional) skip industry-code companies with fewer staff
  site_keywords        words looked for on websites; the hit count drives the automatic screen
  min_site_hits        hits needed for an industry-code company to reach review (2–3)
  search_queries       15–25 local-language web searches, including city variants
  directories          directory names/categories for web search with allowed_domains
  zl_categories        (Latvia) zl.lv category slugs read by `directories`
```

## How Claude picks keywords

- Use the country's language(s) plus English. For Finland add Swedish; for Latvia add Russian
  for web searches; for Estonia add Russian; for Belgium French and Dutch, and so on.
- Use word stems, not full words, so endings and compounds match (`mainostuot` → mainostuotteet).
- Strong = words that almost only this niche uses in a company name. Weak = common words.
- Industry codes: pick the 3–6 national codes where these companies are usually registered.
  The website check filters out the rest, so a slightly broad code is fine; a very broad one
  (e.g. all advertising agencies) only when there are clear site keywords.
- Search phrases: what a buyer would type ("logo mugs for company"), the niche's own words,
  and "<niche word> <city>" for the 10–15 largest cities.
