"""Tradier Broker Backend

A backend implementation for interfacing with Tradier
"""
import os
import string
import sys
from collections import namedtuple
from datetime import date

import alpaca_trade_api
import logbook
import pandas
import requests
from dateutil.parser import parse
from exchange_calendars import get_calendar, register_calendar_alias
from exchange_calendars.calendar_utils import (
    global_calendar_dispatcher as default_calendar,
)
from pylivetrader.assets import Equity
from pylivetrader.backend.base import BaseBackend
from pylivetrader.finance.order import ORDER_STATUS, Order
from pylivetrader.protocol import Account, Portfolio, Position, Positions
from tiingo import TiingoClient

logbook.StreamHandler(sys.stdout).push_application()
log = logbook.Logger("Tradier")

NY = "America/New_York"
end_offset = pandas.Timedelta("1000 days")
one_day_offset = pandas.Timedelta("1 day")

tiingo_client = TiingoClient()


Asset = namedtuple("Asset", "id name symbol exchange status tradable")


class Backend(BaseBackend):
    """Tradier backend"""

    def __init__(self, url=None, version="v1", account=None, bearer=None):
        self._url = url or os.environ.get("TRADIER_URL")
        if self._url is None:
            raise ValueError("Missing Tradier base url")

        self._account = account or os.environ.get("TRADIER_ACCOUNT")
        if self._account is None:
            raise ValueError("Missing Tradier account")

        self._bearer = bearer or os.environ.get("TRADIER_API_BEARER")
        if self._bearer is None:
            raise ValueError("Missing Tradier bearer token")

        self._version = version

        #  we'll use these same headers over and over again
        self._headers = dict(
            Authorization="Bearer {}".format(self._bearer), Accept="application/json"
        )

        # self._api = tradeapi.REST(
        #     None, None, None, api_version='v1'
        # )

    def _form_url(self, endpoint):
        """Make it easy to form the urls"""

        base = "https://{url}/{version}".format(url=self._url, version=self._version)
        components = (base, endpoint)
        almost_there = "/".join(x.strip("/") for x in components)
        complete_url = almost_there.replace("[[account]]", self._account)

        return complete_url

    def _list_assets(self, asset_class="equities"):
        # Here is an example of what is cominng through Alpaca's assets API
        # {
        #     "id": "904837e3-3b76-47ec-b432-046db621571b",
        #     "class": "us_equity",
        #     "exchange": "NASDAQ",
        #     "symbol": "AAPL",
        #     "name": "Apple Inc. Common Stock",
        #     "status": "active",
        #     "tradable": true,
        #     "marginable": true,
        #     "shortable": true,
        #     "easy_to_borrow": true,
        #     "fractionable": true,
        #     "maintenance_margin_requirement": 30
        # }
        desirable_characters = string.ascii_letters + string.digits

        symbols = [
            Asset(
                id=x["ticker"],
                symbol=x["ticker"],
                exchange=x["exchange"],
                name=x["ticker"],
                status="active",
                tradable=True,
            )
            for x in tiingo_client.list_stock_tickers()
            if x["exchange"] in ("NYSE", "NASDAQ", "AMEX") and x["endDate"]
            # and parse(x["endDate"]).date() == date.today()  # presently active
            and all([y in desirable_characters for y in x["ticker"]])
        ]

        return symbols

    def get_equities(self):
        log.info("Fetching equities")

        assets = []
        # t = normalize_date(pandas.Timestamp('now', tz=NY))
        t = pandas.Timestamp("now", tz=NY).normalize()
        # raw_assets = self._api.list_assets(asset_class='us_equity')
        raw_assets = self._list_assets(asset_class="us_equity")
        for raw_asset in raw_assets:
            asset = Equity(
                raw_asset.id,
                raw_asset.exchange,
                symbol=raw_asset.symbol,
                asset_name=raw_asset.symbol,
            )

            asset.start_date = t - one_day_offset

            if raw_asset.status == "active" and raw_asset.tradable:
                asset.end_date = t + end_offset
            else:
                # if asset is not tradable, set end_date = day before
                asset.end_date = t - one_day_offset
            asset.auto_close_date = asset.end_date

            assets.append(asset)

            # register all unseen exchange name as
            # alias of NYSE (e.g. AMEX, ARCA, NYSEARCA.)
            if not default_calendar.has_calendar(raw_asset.exchange):
                register_calendar_alias(raw_asset.exchange, "NYSE", force=True)

        return assets

    @property
    def positions(self):
        resp = requests.get(
            url=self._form_url("/accounts/[[account]]/positions"), headers=self._headers
        )

        pos_dict = Positions()

        if resp.status_code == 200:
            respj = resp.json()

            if respj["positions"] == "null":
                return pos_dict

            elif isinstance(respj["positions"]["position"], list):
                for obj in respj["positions"]["position"]:
                    #  TODO: have to use Equity/Asset objects as the key
                    pos = Position(obj["symbol"])
                    pos.amount = obj["quantity"]
                    pos.cost_basis = obj["cost_basis"] / obj["quantity"]

                    pos_dict[pos.asset] = pos

            else:  # a single position sits by itself for some reason
                obj = respj["positions"]["position"]

                pos = Position(obj["symbol"])
                pos.amount = obj["quantity"]
                pos.cost_basis = obj["cost_basis"] / obj["quantity"]

                pos_dict[pos.asset] = pos

        else:
            log.error("Error trying to get positions: {}".format(resp.text))

        return pos_dict

    @property
    def portfolio(self):
        resp = requests.get(
            url=self._form_url("/accounts/[[account]]/balances"), headers=self._headers
        )

        portfolio = Portfolio()

        if resp.status_code == 200:
            respj = resp.json()["balances"]

            portfolio.portfolio_value = respj["total_equity"]
            portfolio.cash = respj["total_cash"]
            portfolio.positions = self.positions
            portfolio.positions_value = respj["market_value"]

        else:
            log.error("Error in getting portfolio: {}".format(resp.text))

        return portfolio

    @property
    def account(self):
        resp = requests.get(
            url=self._form_url("/accounts/[[account]]/balances"), headers=self._headers
        )

        account = Account()

        if resp.status_code == 200:
            respj = resp.json()["balances"]

            account.settled_cash = respj["cash"]["cash_available"]
            account.buying_power = respj["total_cash"]
            account.total_positions_value = respj["market_value"]
            account.total_positions_exposure = respj["market_value"]
            account.available_funds = respj["cash"]["cash_available"]
            account.net_liquidation = respj["total_equity"]

        else:
            log.error("Error in getting account: {}".format(resp.text))

        return account

    def order(self, asset, amount, style, quantopian_compatible=True):
        log.info("skipping order()")

    def batch_order(self, args):
        return [self.order(*order) for order in args]

    @property
    def orders(self, quantopian_compatible=True):
        raise NotImplementedError("orders() is not implemented for Tradier backend")

    def get_order(self, order_id):
        resp = requests.get(
            url=self._form_url(
                "/accounts/[[account]]/orders/{order_id}".format(order_id=order_id)
            ),
            headers=self._headers,
        )

        if resp.status_code == 200:
            #  import symbol here for testing purposes
            from pylivetrader.api import symbol

            tradier_order = resp.json()["order"]

            order = Order(
                id=tradier_order["id"],
                asset=symbol(tradier_order["symbol"]),
                amount=(
                    int(tradier_order["quantity"])
                    if tradier_order["side"] == "buy"
                    else -int(tradier_order["quantity"])
                ),
                dt=pandas.Timestamp(tradier_order["create_date"]),
                commission=3.49,
            )

            status = tradier_order["status"]

            if status in ("filled", "partially_filled"):
                order._status = ORDER_STATUS.FILLED
                order.filled = int(tradier_order["exec_quantity"])
            elif status == "cancelled":
                order._status = ORDER_STATUS.CANCELLED
            elif status == "rejected":
                order._status = ORDER_STATUS.REJECTED
            else:
                order._status = ORDER_STATUS.OPEN

            return order

        else:
            log.error("Error getting order: {}".format(resp.text))

            return None

    def all_orders(self, before=None, status="all", days_back=None, initialize=False):
        """status can be 'all', 'open' or 'closed'"""

        return {}

        resp = requests.get(
            url=self._form_url("/accounts/[[account]]/orders"), headers=self._headers
        )

        if resp.status_code == 200:
            trd_orders = resp.json()["orders"]["order"]

            return orders

        else:
            log.error("Error in getting all orders: {}".format(resp.text))

            return None

    def get_last_traded_dt(self, asset):
        resp = requests.get(
            url=self._form_url("/markets/quotes"),
            headers=self._headers,
            params=dict(symbols=asset.symbol),
        )

        if resp.status_code == 200:
            security = resp.json()["quotes"]["quote"]

            #  handle last_traded as pandas Timestamp
            dt = pandas.Timestamp(security["trade_date"], tz=NY, unit="ms")

            return dt

        else:
            log.error("Error in getting last traded dt: {}".format(resp.text))

            return None

    def get_spot_value(
        self, assets, field, dt, date_frequency, quantopian_compatible=True
    ):
        if field not in (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "price",
            "last_traded",
        ):
            raise ValueError('"{}" is not a valid field'.format(field))

        if field in ("price", "close"):
            #  use last in place of close also since the minute is still open
            field = "last"

        if field == "last_traded":
            field = "trade_date"

        assets_is_scalar = not isinstance(assets, (list, set, tuple))
        if assets_is_scalar:
            symbols = [assets.symbol]
        else:
            symbols = [asset.symbol for asset in assets]

        #  TODO: figure out how to handle large set of assets

        resp = requests.get(
            url=self._form_url("/markets/quotes"),
            headers=self._headers,
            params=dict(symbols=",".join(symbols)),
        )

        if resp.status_code == 200:
            securities = resp.json()["quotes"]["quote"]

            if isinstance(securities, list):
                values = [sec[field] for sec in securities]
            else:
                values = [securities[field]]

            #  handle last_traded as pandas Timestamp
            if field == "trade_date":
                values = [pandas.Timestamp(x, tz=NY, unit="ms") for x in values]

            return values[0] if assets_is_scalar else values

        else:
            log.error("Error in getting spot value: {}".format(resp.text))

            return None

    def get_bars(self, assets, data_frequency, bar_count=500, end_dt=None):
        assets_is_scalar = not isinstance(assets, (list, set, tuple))
        assert "min" in data_frequency  # can update to support daily later
        if assets_is_scalar:
            symbols = [assets.symbol]
        else:
            symbols = [asset.symbol for asset in assets]

        df = self._fetch_bars_from_api(
            symbols, "day" if is_daily else "minute", to=end_dt, limit=bar_count
        )

        # change the index values to assets to compatible with zipline
        symbol_asset = (
            {a.symbol: a for a in assets}
            if not assets_is_scalar
            else {assets.symbol: assets}
        )
        df.columns = df.columns.set_levels(
            [symbol_asset[s] for s in df.columns.levels[0]], level=0
        )
        # try:
        #     df.columns = df.columns.set_levels([
        #         symbol_asset[s] for s in df.columns.levels[0]], level=0)
        # except:
        #     pass
        return df

    def _fetch_bars_from_api(self, symbols, size, _from=None, to=None, limit=None):
        """
        Query history bars either minute or day in parallel
        for multiple symbols

        you can pass:
        1 _from + to
        2 to + limit
        3 limit, this way will use the current time as to

        symbols: list[str]
        size:    str ('day', 'minute')
        _from:   str or pd.Timestamp
        to:      str or pd.Timestamp
        limit:   str or int

        return: MultiIndex dataframe that looks like this:
                       AA                          GOOG
                       open high low close volume  open high low close volume
        DatetimeIndex:

        columns: level 0 equity name, level 1 OHLCV

        """
        assert size in ("day", "minute")

        assert (_from and to) or limit

        if not (_from and to):
            _from, to = self._get_from_and_to(size, limit, end_dt=to)
        # alpaca support get real-time data of multi stocks(<200) at once
        parts = []
        for i in range(0, len(symbols), ALPACA_MAX_SYMBOLS_PER_REQUEST):
            part = symbols[i : i + ALPACA_MAX_SYMBOLS_PER_REQUEST]
            parts.append(part)
        args = [
            {"symbols": part, "_from": _from, "to": to, "size": size, "limit": limit}
            for part in parts
        ]
        # result2 = parallelize(self._fetch_bars_from_api_internal)(args)
        result = parallelize_with_multi_process(self._fetch_bars_from_api_internal)(
            args
        )

        return pd.concat(result, axis=1)

    def _get_from_and_to(self, size, limit, end_dt=None):
        """
        this method returns the trading time range. if end_dt is not
        a session time，it will be adjusted to the nearest last trading
        minute. when size=daily, will return a timestamp of midnight.

        return: tuple(pd.Timestamp(tz=America/New_York))
        """
        if not end_dt:
            end_dt = pd.to_datetime("now", utc=True).floor("min")
        session_label = self._cal.minute_to_session_label(end_dt)
        all_minutes: pd.DatetimeIndex = self._cal.all_minutes
        all_sessions: pd.DatetimeIndex = self._cal.all_sessions
        if size == "minute":
            if end_dt not in self._cal.minutes_for_session(session_label):
                end_dt = self._cal.previous_minute(end_dt)
                # Alpaca's last minute is 15:59 not 16:00 (NY tz)
                end_dt = end_dt - timedelta(minutes=1)
            idx = all_minutes.get_loc(end_dt)
            start_minute = (
                all_minutes[idx - limit + 1] if limit != 1 else all_minutes[idx - limit]
            )
            _from = start_minute.tz_convert(NY)
            to = end_dt.tz_convert(NY)
        elif size == "day":
            idx = all_sessions.get_loc(session_label)
            start_session = all_sessions[idx - limit + 1]
            _from = start_session.tz_localize(None).tz_localize("America/New_York")
            to = session_label.tz_localize(None).tz_localize("America/New_York")

        return _from, to

    def _fetch_bars_from_api_internal(self, params):
        """
        this method is used by parallelize_with_multi_process or parallelize.
        params: dict with keys in ['symbols', '_from', 'to', 'size']
        """

        @skip_http_error((404, 504))
        def wrapper():
            symbols = params["symbols"]  # symbols can be list or str
            _from = params["_from"]
            to = params["to"]
            size = params["size"]

            timeframe = TimeFrame.Minute if size == "minute" else TimeFrame.Day

            # Using V2 api to get the data. we cannot do 1 api call for all
            # symbols because the v1 `limit` was per symbol, where v2 it's for
            # overall response size; so we will iterate over each symbol with
            # the limit for each to replicate that behaviour
            r = {}
            for sym in symbols:
                r[sym] = self._api.get_bars(
                    sym,
                    limit=params["limit"],
                    timeframe=timeframe,
                    start=_from.isoformat(),
                    end=to.isoformat(),
                    adjustment="raw",
                ).df
            df = pd.concat(r, axis=1)
            # data is received in UTC tz but without tz (naive)
            df.index = df.index.tz_localize("UTC")

            if size == "minute":
                df.index += pd.Timedelta("1min")

                if not df.empty:
                    # mask out bars outside market hours
                    mask = self._cal.minutes_in_range(
                        df.index[0],
                        df.index[-1],
                    ).tz_convert(NY)
                    df = df.reindex(mask)
            return df

        return wrapper()
