"""v8 - the asset catalog is the single source of truth for the ETL, portfolios, forecast and UI."""
import pytest
from matplotlib.figure import Figure

from src.app import views
from src.config.settings import (
    ASSET_CATALOG, ASSET_INFO, CASH_TICKER, GROUP_ORDER, SCHEMA_SQL_PATH, TICKER_UNIVERSE,
)
from src.forecast.projection import ASSUMPTIONS
from src.portfolio.allocation import MODEL_PORTFOLIOS, RATIONALE, target_allocation
from src.portfolio.rationale import ASSET_GROUPS, group_weights

VALID_CLASSES = {"equity_etf", "equity_stock", "crypto", "metal", "cash"}


def test_catalog_has_no_duplicates_and_valid_fields():
    tickers = [a["ticker"] for a in ASSET_CATALOG]
    assert len(tickers) == len(set(tickers)) and len(tickers) >= 13
    for a in ASSET_CATALOG + [ASSET_INFO[CASH_TICKER]]:
        assert a["asset_class"] in VALID_CLASSES
        assert a["group"] in GROUP_ORDER
        assert 0 <= a["vol"] < 2 and -0.5 < a["ret"] < 0.5 and a["why"] and a["name"]


def test_asset_classes_match_database_check_constraint():
    sql = SCHEMA_SQL_PATH.read_text()
    for cls in VALID_CLASSES:
        assert f"'{cls}'" in sql


def test_everything_is_derived_from_the_catalog():
    assert {t for t, _, _ in TICKER_UNIVERSE} == {a["ticker"] for a in ASSET_CATALOG}
    assert set(ASSUMPTIONS) == set(ASSET_INFO) and set(RATIONALE) == set(ASSET_INFO)
    assert {t for ts in ASSET_GROUPS.values() for t in ts} == set(ASSET_INFO)


@pytest.mark.parametrize("name", list(MODEL_PORTFOLIOS))
def test_every_profile_covers_whole_catalog_and_sums_to_100(name):
    alloc = MODEL_PORTFOLIOS[name]
    assert set(alloc) == set(ASSET_INFO) and sum(alloc.values()) == 100
    assert all(v >= 0 for v in alloc.values())


def test_new_etfs_are_actually_used():
    used = {t for alloc in MODEL_PORTFOLIOS.values() for t, v in alloc.items() if v > 0}
    for ticker in ("SCHD", "VWO", "VTIP", "SHV", "VNQ"):
        assert ticker in used


def test_risk_ladder_stock_and_bond_share():
    def share(name, group):
        return sum(v for t, v in MODEL_PORTFOLIOS[name].items() if ASSET_INFO[t]["group"] == group)
    order = ["Conservative", "Moderate", "Growth", "Aggressive"]
    stocks = [share(n, "U.S. stocks") + share(n, "International stocks") for n in order]
    bonds = [share(n, "Bonds") + share(n, "Cash") for n in order]
    assert stocks == sorted(stocks) and bonds == sorted(bonds, reverse=True)


@pytest.mark.parametrize("name", list(MODEL_PORTFOLIOS))
@pytest.mark.parametrize("years", [1, 2, 3, 10])
def test_short_horizon_rule_still_holds_with_new_etfs(name, years):
    alloc = target_allocation(name, years)
    assert sum(alloc.values()) == pytest.approx(100)
    if years < 3:
        assert alloc["BTC-USD"] == 0 and alloc["ETH-USD"] == 0


def test_group_totals_and_figures():
    alloc = [{"ticker": t, "allocation_pct": p, "amount": p * 100, "rationale": ""}
             for t, p in target_allocation("Growth", 10).items() if p > 0]
    totals = views.group_totals(alloc)
    assert sum(totals.values()) == pytest.approx(100) and list(totals) == [g for g in GROUP_ORDER if g in totals]
    assert totals["Crypto"] == 7
    assert group_weights(alloc)["Crypto"] == 7
    assert isinstance(views.allocation_figure(alloc), Figure) and isinstance(views.holdings_figure(alloc), Figure)


def test_asset_catalog_table_lists_all_assets_plus_cash():
    df = views.asset_catalog_table()
    assert len(df) == len(ASSET_CATALOG) + 1 and CASH_TICKER in set(df["Ticker"])
