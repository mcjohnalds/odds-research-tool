import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_URL = "https://v3.football.api-sports.io"
LEAGUE_ID = 253
LEAGUE_NAME = "Major League Soccer"
MATCH_DATE = "2024-10-19"
MAX_REQUESTS = 5
SEASON = 2024
TIMEZONE = "America/New_York"
ROOT = Path(__file__).parent
CACHE_PATH = ROOT / "cache.json"

type APIQueryParameters = dict[str, str | int]


class APIPaging(TypedDict):
    total: int


class APIResponse(TypedDict):
    errors: object
    paging: APIPaging
    response: list[object]


class APITeam(TypedDict):
    id: int
    name: str


class APIFixtureDetails(TypedDict):
    id: int
    date: str


class APIFixtureTeams(TypedDict):
    home: APITeam
    away: APITeam


class APIFixture(TypedDict):
    fixture: APIFixtureDetails
    teams: APIFixtureTeams


class APIStanding(TypedDict):
    rank: int
    team: APITeam
    group: str


class APIStandingLeague(TypedDict):
    standings: list[list[APIStanding]]


class APIStandings(TypedDict):
    league: APIStandingLeague


class GameOdds(TypedDict):
    bookmaker: str
    home: float
    draw: float
    away: float


class TeamRanking(TypedDict):
    rank: int
    group: str
    group_size: int


class SportsData(TypedDict):
    date: str
    generated_at: str
    fixtures: list[APIFixture]
    standings: list[APIStandings]


class Game(TypedDict):
    kickoff: str
    home: str
    away: str
    home_rank: int | None
    home_rank_total: int | None
    away_rank: int | None
    away_rank_total: int | None
    conference: str | None
    odds: GameOdds | None
    undervalued: str | None


class ApiClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.requests_sent = 0

    def get[T](self, path: str, parameters: APIQueryParameters) -> list[T]:
        results: list[object] = []
        page: int | None = None
        while True:
            if self.requests_sent >= MAX_REQUESTS:
                message = f"API request limit of {MAX_REQUESTS} reached"
                raise RuntimeError(message)
            query_parameters = parameters
            if page is not None:
                query_parameters = {**parameters, "page": page}
            query = urlencode(query_parameters)
            url = f"{BASE_URL}/{path}?{query}"
            request = Request(url, headers={"x-apisports-key": self.api_key})
            self.requests_sent += 1
            with urlopen(request, timeout=20) as response:
                data = cast(APIResponse, json.load(response))
            if data["errors"]:
                raise RuntimeError(str(data["errors"]))
            results.extend(data["response"])
            total_pages = data["paging"]["total"]
            if total_pages <= 1:
                return cast(list[T], results)
            if page is None:
                page = 2
            elif page >= total_pages:
                return cast(list[T], results)
            else:
                page += 1


def get_sports_data(date: str, season: int) -> SportsData:
    try:
        cached = json.loads(CACHE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        cached = None
    if isinstance(cached, dict) and cached.get("date") == date:
        return cast(SportsData, cached)

    api_key = os.environ.get("API_FOOTBALL_API_KEY")
    if not api_key:
        raise RuntimeError("API_FOOTBALL_API_KEY is required")

    client = ApiClient(api_key)
    common = {"league": LEAGUE_ID, "season": season}
    fixtures: list[APIFixture] = client.get(
        "fixtures", {**common, "timezone": TIMEZONE}
    )
    generated_at = datetime.now(ZoneInfo(TIMEZONE)).isoformat(
        timespec="seconds"
    )
    cache: SportsData = {
        "date": date,
        "generated_at": generated_at,
        "fixtures": [
            item
            for item in fixtures
            if item["fixture"]["date"].startswith(date)
        ],
        "standings": client.get("standings", common),
    }
    CACHE_PATH.write_text(json.dumps(cache, indent=2) + "\n")
    return cache


def ranking_by_team(
    standings: list[APIStandings],
) -> dict[int, TeamRanking]:
    groups = standings[0]["league"]["standings"] if standings else []
    group_sizes = {
        row["group"]: max(item["rank"] for item in group)
        for group in groups
        for row in group
    }
    return {
        row["team"]["id"]: {
            "rank": row["rank"],
            "group": row["group"],
            "group_size": group_sizes[row["group"]],
        }
        for group in groups
        for row in group
    }


def mock_odds_by_fixture(fixtures: list[APIFixture]) -> dict[int, GameOdds]:
    odds: dict[int, GameOdds] = {}
    for item in fixtures:
        fixture_id = item["fixture"]["id"]
        generator = random.Random(fixture_id)
        home_probability = generator.uniform(0.3, 0.5)
        draw_probability = generator.uniform(0.22, 0.29)
        away_probability = 1 - home_probability - draw_probability
        margin = 1.05
        odds[fixture_id] = {
            "bookmaker": "Mock odds",
            "home": round(1 / (home_probability * margin), 2),
            "draw": round(1 / (draw_probability * margin), 2),
            "away": round(1 / (away_probability * margin), 2),
        }
    return odds


def build_games(data: SportsData) -> list[Game]:
    rankings = ranking_by_team(data["standings"])
    odds = mock_odds_by_fixture(data["fixtures"])
    games: list[Game] = []
    for item in data["fixtures"]:
        fixture_id = item["fixture"]["id"]
        home = item["teams"]["home"]
        away = item["teams"]["away"]
        home_ranking = rankings.get(home["id"])
        away_ranking = rankings.get(away["id"])
        home_rank = home_ranking["rank"] if home_ranking else None
        home_rank_total = home_ranking["group_size"] if home_ranking else None
        away_rank = away_ranking["rank"] if away_ranking else None
        away_rank_total = away_ranking["group_size"] if away_ranking else None
        home_group = home_ranking["group"] if home_ranking else None
        away_group = away_ranking["group"] if away_ranking else None
        if home_group == away_group:
            conference = home_group
        elif home_group and away_group:
            conference = f"{home_group} / {away_group}"
        else:
            conference = home_group or away_group
        game_odds = odds.get(fixture_id)
        undervalued = None
        same_group = bool(
            home_ranking
            and away_ranking
            and home_ranking["group"] == away_ranking["group"]
        )
        if (
            game_odds
            and same_group
            and home_rank is not None
            and away_rank is not None
            and home_rank != away_rank
        ):
            if home_rank < away_rank:
                higher_odds = game_odds["home"]
                lower_odds = game_odds["away"]
                higher_team = home["name"]
            else:
                higher_odds = game_odds["away"]
                lower_odds = game_odds["home"]
                higher_team = away["name"]
            if 1 / higher_odds < 1 / lower_odds:
                undervalued = higher_team
        kickoff = datetime.fromisoformat(item["fixture"]["date"])
        games.append(
            {
                "kickoff": kickoff.strftime("%H:%M"),
                "home": home["name"],
                "away": away["name"],
                "home_rank": home_rank,
                "home_rank_total": home_rank_total,
                "away_rank": away_rank,
                "away_rank_total": away_rank_total,
                "conference": conference,
                "odds": game_odds,
                "undervalued": undervalued,
            }
        )
    return games


def main() -> None:
    data = get_sports_data(MATCH_DATE, SEASON)
    template = Environment(
        loader=FileSystemLoader(ROOT),
        autoescape=select_autoescape(),
    ).get_template("template.html")
    html = template.render(
        league=LEAGUE_NAME,
        date=MATCH_DATE,
        games=build_games(data),
    )
    (ROOT / "index.html").write_text(html)


if __name__ == "__main__":
    main()
