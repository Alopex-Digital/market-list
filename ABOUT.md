# market-list (skill)

Claude Code skill: finds every company of one kind in one European country and delivers a 4-tab Excel with registry data, money figures and contacts.

| | |
|---|---|
| **Who uses it** | Martin, Artem, anyone doing market mapping (also shared publicly) |
| **Status** | ✅ Current (built 10.11.2026 for 9to4: promo resellers FI + LV) |
| **Type** | Claude skill |
| **Source (GitHub)** | https://github.com/Alopex-Digital/market-list |
| **Drive** | Internal_Tools / market-list (skill) (README, latest zip) |
| **Owner** | Mikita Kutsenka |

## What it does
- You describe the companies ("sell logo products to businesses") and the country; Claude picks local search words and industry codes.
- Sweeps the national registry (Finland, Latvia built in), directories and the web; scripts check every website; Claude reviews.
- Adds staff, taxes or revenue, generic emails, phones, board members and decision makers (Clay free search; paid emails only if you agree).
- Saves progress after every step: `/market-list continue` resumes after a limit.

## Install (Claude Code)
```
/plugin marketplace add Alopex-Digital/market-list
/plugin install market-list@alopex-tools
```
Then type `/market-list`. Setup asks for Python, Node.js and a Clay account (14-day trial, then free plan).

---
_This page is published automatically from `market-list/ABOUT.md` whenever the tool changes._
