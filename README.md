# market-list

A Claude Code skill that finds **every company of one kind in one European country** and gives
you a clean Excel file: registry number, status, staff, taxes or revenue, generic emails, phones
and the people who run the company.

Example: "all companies in Finland that sell promotional products with a logo to businesses".

You answer a few questions in plain language. Claude works out the local search words and
industry codes, sweeps the national company registry, searches the web and business directories,
checks every website, sorts the results, collects contacts and writes the Excel. If Claude hits
its usage limits halfway, everything is saved: type `/market-list continue` later.

## Install

You need Claude Code, Python 3.8+ and Node.js (for the Clay connection).

```
/plugin marketplace add mickeyalopex/market-list
/plugin install market-list@alopex-tools
```

Then type `/market-list`. The first time, it walks you through setup:

1. It checks Python and installs one small package (openpyxl, for Excel).
2. It connects **Clay** (required, used to find decision makers) through a small bridge that both
   Claude and the skill's scripts share, so people search runs without using your Claude limits. Searching is free; finding
   email addresses costs Clay credits. A new Clay account has a 14-day trial with about 1,000
   credits (roughly 300–500 emails); after that the free plan gives 100 credits a month. The skill
   explains your options when credits run out.
3. It asks where to keep your projects (default `~/market-list`).

To update later: `/plugin marketplace update alopex-tools`.

## What you get

An Excel file with 4 tabs:

| Tab | Contents |
|---|---|
| Companies | Brand, website, legal name, reg. no, proof found (optional), employees (2 years), taxes or revenue, status, note |
| Generic contacts | Company, reg. no, website, generic email (info@, sales@ …), phone |
| People | Name, role, email, email type (named / guessed – verify), source, LinkedIn |
| How it was searched | Sources, keywords, codes, counts, what each column means |

If you give it your existing list, the result shows only the companies you did not have, and
tells you how many of yours it found again.

## Which countries

Any European country works. Finland and Latvia have built-in registry modules (full registry
sweep, staff, money figures, board members, all free). For other countries the skill uses web
search, business directories and Clay; see `skills/market-list/reference/countries.md` for what
free data each country has. Modules for Estonia, Norway, Czechia, France and Romania are the
next easy additions (their registries are free and open).

## Costs

- Registry data, web search, website checks: free.
- Your Claude usage: a full country run uses a good part of a day's limits. The website checks
  run as Python scripts, not through Claude, so they do not count.
- Clay: free for people search; paid only if you choose to find emails at the end (it asks first).

## Good to know

- The skill never sends emails or messages; it only reads public websites and open data.
- The list contains business contacts of real people: use them for relevant B2B outreach, let
  people opt out, and delete what you do not need.
- "Proof on websites" (for example a supplier's product codes) is off by default because it is
  slower and uses more Claude limits; switch it on when you need it.

## Under the hood

`skills/market-list/engine/ml.py` is a command-line tool. Every step saves to a project folder,
and `status` shows where a project stands:

`new` → `registry` → `directories` → `add` (web finds) → `lookup` → `guess-sites` → `scan` →
`screen` → `review`/`decide` → `finance` → `contacts` → `people-clay` → `existing` → `export`

Claude drives it, but you can run it yourself: `python3 ml.py --help`. Only one command can write
to a project at a time; long steps save every 30 seconds, so stopping one loses almost nothing.

## Adding a country

A country module (`engine/countries/<code>.py`) has four functions: `sweep` (registry candidates),
`lookup` (registry data for companies found on the web), `finance` (staff and money figures) and
`people` (board members). `countries/fi.py` and `countries/lv.py` are full examples;
`reference/countries.md` lists the free sources per country.

License: MIT.
