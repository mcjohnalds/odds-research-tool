# Sports Odds Research Tool

A research tool for sports bettors. It pulls Major League Soccer data and flags
undervalued odds.

## Run

Requires [uv](https://docs.astral.sh/uv/).

[Create a free Api-Football key](https://www.api-football.com/) then run:

```
API_FOOTBALL_API_KEY=<key> uv run main.py
```

The script gets sports data from Api-Football and generates `index.html`.

"Favorite Undervalued" means the higher-ranked team has lower implied win
probability than its lower-ranked opponent.

## Caching

Sports data is cached and updates at most once per day. So you can run the
program many times and not exceed the Api-Football rate limit. Delete
`cache.json` to clear the cache.

## Linting

Format Python with `ruff format`.

Lint Python with `ruff check`.

Keep lines in the HTML file under 80 characters.
