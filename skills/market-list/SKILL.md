---
name: market-list
description: Build a complete list of every company of one kind in one European country (for example all promotional-product resellers in Finland), with registry number, staff, taxes or revenue, status, generic emails, phones and decision makers, exported to a formatted 4-tab Excel file. Works in resumable batches, so it can stop at Claude's limits and continue later. Use when the user types /market-list, asks to "find all companies that ...", "map the market", "list every X in country Y", "check which companies we missed", or wants to continue a market list.
---

# market-list

You build a complete company list for one niche in one country. The heavy work (registry files,
website checks, money data) runs in Python scripts in `engine/`, so it does not use up the
user's Claude limits. You do the parts that need judgement: questions, web search, review,
people search with Clay.

`ENGINE` = the `engine` folder next to this file (use the skill's base directory).
Run every command as `python3 "$ENGINE/ml.py" <command> --project "<project folder>"`.

Speak to the user in plain language. They may not be technical. Never show them raw JSON or
stack traces; say what happened and what comes next. After each stage give a one-line update
("Registry: 1,048 candidates. Now checking their websites, about 10 minutes.").

## 0. Which situation are we in?

- `~/.market-list/config.json` missing → **Setup** (section 1), then section 2.
- User says "continue", or names an existing project → run `status`, tell the user where it
  stands in two lines, then follow its `next:` hint (section 3).
- Otherwise → **New search** (section 2).

## 1. Setup (first time only)

1. Run `python3 "$ENGINE/ml.py" doctor`. If openpyxl is missing, run
   `python3 -m pip install --user openpyxl` (if pip refuses because of a managed Python, use
   `python3 -m pip install --user --break-system-packages openpyxl`), then run doctor again.
2. **Clay is required.** Check whether Clay tools are available (tools named like
   `search-contacts`, `search-companies` from a server called clay). If not, read
   `reference/clay.md` and walk the user through connecting it. Explain the plans in the words
   given there, including what happens after the free trial. Do not continue to section 2 until
   `python3 "$ENGINE/ml.py" doctor --clay` prints "Clay OK".
3. Ask where projects should live (default `~/market-list`). Write
   `~/.market-list/config.json`: `{"projects_dir": "...", "clay": true, "created": "<date>"}`.

## 2. New search: questions

Ask these with the AskUserQuestion tool, a few at a time, with sensible options. Never ask the
user for things they cannot know (search keywords, industry codes): you work those out.

1. **What kind of companies?** Free text ("companies that sell logo products to businesses").
2. **Country?** One country per project. Check `reference/countries.md`: say in one line what
   free data that country has (e.g. "Finland: full registry + revenue and staff for free").
3. **Who counts and who does not?** Propose 3–5 include rules and 3–5 exclude rules from the
   description; the user ticks or edits. Always offer "closed companies: keep, marked closed"
   and "foreign sellers with a local shop: keep, marked".
4. **Do you already have a list?** If yes, get the file path (xlsx/csv). The result will then
   show only new companies, plus how many of theirs were found again.
5. **Proof on websites?** Off by default. Explain: "I can look for signs of a specific supplier,
   brand or software on every website (for example midocean product codes). It makes the run
   slower and uses more of your Claude limits." If yes, ask what to look for.
6. **Contacts:** free contacts are always collected (generic emails, phones, board members,
   named emails on websites, Clay people search). Paid email finding is offered at the end.

Then write the **profile** yourself (`reference/profile.md` explains every field; copy the shape
of `profiles/promo-products.json`). Pick, in the country's language(s):
strong name keywords, weak name keywords, website keywords, industry codes, 15–25 web search
phrases and the directory categories. Show the user a 3-line summary, not the JSON.

Create the project: `new --project "<projects_dir>/<short-name>-<CC>" --country CC --profile <file>`.
Save the profile file inside the project folder too.

## 3. The run (each step can be resumed)

Run `status` whenever unsure. Each command saves its own progress. Long commands
(`registry`, `guess-sites`, `scan`, `finance`) can take 5–40 minutes: run them in the background
and tell the user roughly how long. Only one command may write to a project at a time (the
engine refuses a second one).

1. `registry`: sweep the national registry (built-in countries) by name keywords and industry codes.
2. `directories`: built-in directory readers (e.g. zl.lv for Latvia), if the country has one.
3. **Web search (you):** run the profile's search phrases with WebSearch. Directories that block
   scripts (finder.fi, fonecta.fi, …) still show up in search results: search with
   `allowed_domains` set to the directory and the category name + city names (largest 15–20
   cities, 4–6 per query). Collect every company: name, website if known, city. Write them to
   `<project>/inputs/web_<n>.json` as a list of `{"brand","website","city","found_by"}` and run
   `add --file ... --source web` (or `--source directory`). Optionally run Clay
   `search-companies` (free) with industry + country filters and add those too.
4. `lookup`: match web finds to the registry (registry number, legal name, status).
5. `guess-sites`: try name-based domains for companies without a website.
6. `scan` (add `--proof` if proof is on): opens every website with a script and reads home,
   contact and about pages: keywords, emails, phones.
7. `screen`: automatically drops industry-code-only companies whose website does not mention
   the topic.
8. **Review (you):** `review --next 30` prints compact lines. Decide each one: `in`, `out` or
   `unsure`, with `kind` (reseller / agency / print shop with promo dept / wholesaler / …) and a
   short `note`. Mark foreign companies with `"foreign": "EE"`. Save as JSON
   `[{"id","decision","kind","note"}]` and run `decide --file`. Repeat until none are waiting.
   Rules: follow the profile include/exclude lists; when the website is unreachable or missing
   but the name clearly fits, use `unsure`; never guess `in` for a name that only sounds right.
   For companies without a website that look relevant, `needs-site` lists them: find the site
   with one WebSearch each and `set --id X --website URL`, then `scan` again.
9. `finance`: staff and money figures for in/unsure companies (slow on purpose: polite to sites).
10. `contacts`: generic emails and phones from websites, board members from the registry,
    named emails, and guessed emails when the company's own email pattern is known (marked
    "guessed – verify").
11. **People with Clay (free search):** `people-clay` (background, ~1 min per 10 companies). It sends
    the company domains to Clay 10 at a time and saves names, titles and LinkedIn links to disk, so
    the results do not fill your context. Add `--include-unsure` to search unsure companies too.
    If it reports a Clay error, check the connection (section 1) and run it again; it continues.
    Small owner-run companies are often not on LinkedIn: expect people for roughly a third of them;
    registry board members and website emails cover many of the rest.
12. **Paid emails (ask first):** say how many people have no email and what it costs in Clay
    credits (Email ≈ 1–3 credits per person found). Only on a clear yes: every Clay person in
    `people.json` carries `clay_task` and `clay_entity`; call Clay `add-contact-data-points` with
    that taskId, `[{"type":"Email"}]` and the entityIds (group by task), read results with
    `get-task-context`, then `people-add --file` with `{"domain","name","email","email_type":"named (Clay)"}`.
13. `existing --file <their list>` if they gave one.
14. `export` (add `--only-new` when they gave a list). Tell the user the file path and the
    numbers: companies in, unsure, closed, with generic email, people, people with email.

When you hit a limit mid-run: say what is done, that everything is saved, and that typing
`/market-list continue` picks it up.

## 4. Rules

- Read-only on the outside world: never send emails, never submit forms, never log in to sites.
- Be polite to websites: keep the engine's delays; don't raise thread counts above 24.
- Never print or save API keys. Clay login stays in Claude Code's MCP settings.
- Personal data: collect only business contact details. Read `reference/legal.md` and give the
  user its two-line note with the final file.
- If a step fails, fix and rerun that step; the project keeps everything done so far.
