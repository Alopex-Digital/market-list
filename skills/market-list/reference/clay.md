# Connecting Clay

Clay finds the people (owners, managers) at each company. Searching for people and companies
is free; finding their email addresses costs Clay credits.

## Connect (one time, about 3 minutes)

The skill's engine and Claude share one Clay login through a small bridge (needs Node.js; check
with `npx --version`, install from nodejs.org if missing).

1. In a terminal, run:
   `claude mcp add --scope user clay -- npx -y mcp-remote@0.1.37 https://api.clay.com/v3/mcp`
2. Restart Claude Code. The first time Clay is used, a browser page opens: log in to Clay (or
   create an account) and allow access. The login is saved in `~/.mcp-auth`.
3. Ask Claude to check the connection. It calls `get-current-workspace`, which should answer
   with your workspace name. Then run `python3 <engine>/ml.py doctor`; it also checks the bridge.

(Claude Code can also connect Clay directly with `claude mcp add --transport http clay
https://api.clay.com/v3/mcp`, but then the engine cannot reuse the login, and people search runs
through Claude instead, which uses much more of your Claude limits.)

If the browser cannot reach the login page from where Claude Code runs (for example on a remote
server), open the link on a computer where you are logged in to Clay and paste the final
`localhost` address back to Claude.

## What it costs: tell the user exactly this

- **New account:** a 14-day free trial with about 1,000 credits. That is roughly 300–500 work
  emails, depending on how many email sources Clay has to try per person.
- **After the trial:** the free plan stays: 100 credits a month. Searching people and companies
  keeps working; emails and phone numbers use credits.
- **Paid plan:** "Launch" is about $185 a month (about $167 a month billed yearly). Prices
  change; clay.com/pricing is the reference.

When credits run out, offer three choices:
1. **Connect another Clay account**, for example a colleague's or your company's workspace:
   run `/mcp`, open clay, choose to clear authentication, and log in with the other account.
2. **Top up or upgrade** the current account on clay.com.
3. **Continue on free Clay:** names, roles and LinkedIn profiles, no emails. The list still gets
   generic emails, phones and pattern-based guesses from the free steps.

## Tips

- One Clay request at a time; parallel requests fail with "Too many concurrent requests".
- `search-contacts` takes up to 10 company domains per call.
- Results come back as a taskId: always call `get-task-context` to read them.
- Small owner-run companies are often not on LinkedIn; the registry board members and website
  emails cover those.
