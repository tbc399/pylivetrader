"""Tradier Broker Backend

A backend implementation for interfacing with Tradier
"""

import requests
import logbook
import sys
import pandas
import os

import alpaca_trade_api as tradeapi

from pylivetrader.backend.base import BaseBackend
from pylivetrader.protocol import Position, Positions, Portfolio, Account
from pylivetrader.assets import Equity
from pylivetrader.finance.order import ORDER_STATUS
from pylivetrader.finance.order import Order
from exchange_calendars.calendar_utils import (
    global_calendar_dispatcher as default_calendar,
)
from exchange_calendars import (
    get_calendar,
    register_calendar_alias,
)

logbook.StreamHandler(sys.stdout).push_application()
log = logbook.Logger('Tradier')

NY = 'America/New_York'
end_offset = pandas.Timedelta('1000 days')
one_day_offset = pandas.Timedelta('1 day')


class Backend(BaseBackend):
    """Tradier backend"""
    
    def __init__(self, url=None, version='v1', account=None, bearer=None):
        
        self._url = url or os.environ.get('TRADIER_URL')
        if self._url is None:
            raise ValueError('Missing Tradier base url')
        
        self._account = account or os.environ.get('TRADIER_ACCOUNT')
        if self._account is None:
            raise ValueError('Missing Tradier account')
        
        self._bearer = bearer or os.environ.get('TRADIER_API_BEARER')
        if self._bearer is None:
            raise ValueError('Missing Tradier bearer token')
        
        self._version = version
        
        #  we'll use these same headers over and over again
        self._headers = dict(
            Authorization='Bearer {}'.format(self._bearer),
            Accept='application/json'
        )
        
        # self._api = tradeapi.REST(
        #     None, None, None, api_version='v1'
        # )
    
    def _form_url(self, endpoint):
        """Make it easy to form the urls"""
        
        base = 'https://{url}/{version}'.format(
            url=self._url,
            version=self._version
        )
        components = (base, endpoint)
        almost_there = '/'.join(x.strip('/') for x in components)
        complete_url = almost_there.replace('[[account]]', self._account)
        
        return complete_url
    
    def get_equities(self):
        
        log.info('Fetching equities')
        
        assets = []
        #t = normalize_date(pandas.Timestamp('now', tz=NY))
        t = pandas.Timestamp('now', tz=NY).normalize()
        # raw_assets = self._api.list_assets(asset_class='us_equity')
        raw_assets = self._list_assets(asset_class='us_equity')
        for raw_asset in raw_assets:
            
            asset = Equity(
                raw_asset.id, raw_asset.exchange,
                symbol=raw_asset.symbol,
                asset_name=raw_asset.symbol,
            )
            
            asset.start_date = t - one_day_offset
            
            if raw_asset.status == 'active' and raw_asset.tradable:
                asset.end_date = t + end_offset
            else:
                # if asset is not tradable, set end_date = day before
                asset.end_date = t - one_day_offset
            asset.auto_close_date = asset.end_date
            
            assets.append(asset)
            
            # register all unseen exchange name as
            # alias of NYSE (e.g. AMEX, ARCA, NYSEARCA.)
            if not default_calendar.has_calendar(raw_asset.exchange):
                register_calendar_alias(raw_asset.exchange,
                                        'NYSE', force=True)
        
        return assets
    
    @property
    def positions(self):
        
        resp = requests.get(
            url=self._form_url('/accounts/[[account]]/positions'),
            headers=self._headers
        )
        
        pos_dict = Positions()
        
        if resp.status_code == 200:
            
            respj = resp.json()
            
            if respj['positions'] == 'null':
                
                return pos_dict
            
            elif isinstance(respj['positions']['position'], list):
                
                for obj in respj['positions']['position']:
                    #  TODO: have to use Equity/Asset objects as the key
                    pos = Position(obj['symbol'])
                    pos.amount = obj['quantity']
                    pos.cost_basis = obj['cost_basis'] / obj['quantity']
                    
                    pos_dict[pos.asset] = pos
            
            else:  # a single position sits by itself for some reason
                
                obj = respj['positions']['position']
                
                pos = Position(obj['symbol'])
                pos.amount = obj['quantity']
                pos.cost_basis = obj['cost_basis'] / obj['quantity']
                
                pos_dict[pos.asset] = pos
        
        else:
            
            log.error('Error trying to get positions: {}'.format(resp.text))
        
        return pos_dict
    
    @property
    def portfolio(self):
        
        resp = requests.get(
            url=self._form_url('/accounts/[[account]]/balances'),
            headers=self._headers
        )
        
        portfolio = Portfolio()
        
        if resp.status_code == 200:
            
            respj = resp.json()['balances']
            
            portfolio.portfolio_value = respj['total_equity']
            portfolio.cash = respj['total_cash']
            portfolio.positions = self.positions
            portfolio.positions_value = respj['market_value']
        
        else:
            
            log.error('Error in getting portfolio: {}'.format(resp.text))
        
        return portfolio
    
    @property
    def account(self):
        
        resp = requests.get(
            url=self._form_url('/accounts/[[account]]/balances'),
            headers=self._headers
        )
        
        account = Account()
        
        if resp.status_code == 200:
            
            respj = resp.json()['balances']
            
            account.settled_cash = respj['cash']['cash_available']
            account.buying_power = respj['total_cash']
            account.total_positions_value = respj['market_value']
            account.total_positions_exposure = respj['market_value']
            account.available_funds = respj['cash']['cash_available']
            account.net_liquidation = respj['total_equity']
        
        else:
            
            log.error('Error in getting account: {}'.format(resp.text))
        
        return account
    
    def order(self, asset, amount, style, quantopian_compatible=True):
        log.info('skipping order()')
    
    def batch_order(self, args):
        
        return [self.order(*order) for order in args]
    
    @property
    def orders(self, quantopian_compatible=True):
        
        raise NotImplementedError(
            'orders() is not implemented for Tradier backend'
        )
    
    def get_order(self, order_id):
        
        resp = requests.get(
            url=self._form_url(
                '/accounts/[[account]]/orders/{order_id}'.format(
                    order_id=order_id
                )
            ),
            headers=self._headers
        )
        
        if resp.status_code == 200:
            
            #  import symbol here for testing purposes
            from pylivetrader.api import symbol
            
            tradier_order = resp.json()['order']
            
            order = Order(
                id=tradier_order['id'],
                asset=symbol(tradier_order['symbol']),
                amount=(
                    int(tradier_order['quantity'])
                    if tradier_order['side'] == 'buy'
                    else -int(tradier_order['quantity'])
                ),
                dt=pandas.Timestamp(tradier_order['create_date']),
                commission=3.49
            )
            
            status = tradier_order['status']
            
            if status in ('filled', 'partially_filled'):
                order._status = ORDER_STATUS.FILLED
                order.filled = int(tradier_order['exec_quantity'])
            elif status == 'cancelled':
                order._status = ORDER_STATUS.CANCELLED
            elif status == 'rejected':
                order._status = ORDER_STATUS.REJECTED
            else:
                order._status = ORDER_STATUS.OPEN
            
            return order
        
        else:
            
            log.error('Error getting order: {}'.format(resp.text))
            
            return None
    
    def all_orders(self,
                   before=None,
                   status='all',
                   days_back=None,
                   initialize=False):
        """status can be 'all', 'open' or 'closed'"""
        
        return {}
        
        resp = requests.get(
            url=self._form_url('/accounts/[[account]]/orders'),
            headers=self._headers
        )
        
        if resp.status_code == 200:
            
            trd_orders = resp.json()['orders']['order']
            
            return orders
        
        else:
            
            log.error('Error in getting all orders: {}'.format(resp.text))
            
            return None
    
    def get_last_traded_dt(self, asset):
        
        resp = requests.get(
            url=self._form_url('/markets/quotes'),
            headers=self._headers,
            params=dict(
                symbols=asset.symbol
            )
        )
        
        if resp.status_code == 200:
            
            security = resp.json()['quotes']['quote']
            
            #  handle last_traded as pandas Timestamp
            dt = pandas.Timestamp(security['trade_date'], tz=NY, unit='ms')
            
            return dt
        
        else:
            
            log.error('Error in getting last traded dt: {}'.format(resp.text))
            
            return None
    
    def get_spot_value(
        self, assets, field, dt, date_frequency, quantopian_compatible=True):
        
        if field not in (
            'open', 'high', 'low', 'close',
            'volume', 'price', 'last_traded'):
            raise ValueError('"{}" is not a valid field'.format(field))
        
        if field in ('price', 'close'):
            #  use last in place of close also since the minute is still open
            field = 'last'
        
        if field == 'last_traded':
            field = 'trade_date'
        
        assets_is_scalar = not isinstance(assets, (list, set, tuple))
        if assets_is_scalar:
            symbols = [assets.symbol]
        else:
            symbols = [asset.symbol for asset in assets]
        
        #  TODO: figure out how to handle large set of assets
        
        resp = requests.get(
            url=self._form_url('/markets/quotes'),
            headers=self._headers,
            params=dict(
                symbols=','.join(symbols)
            )
        )
        
        if resp.status_code == 200:
            
            securities = resp.json()['quotes']['quote']
            
            if isinstance(securities, list):
                values = [sec[field] for sec in securities]
            else:
                values = [securities[field]]
            
            #  handle last_traded as pandas Timestamp
            if field == 'trade_date':
                values = [
                    pandas.Timestamp(x, tz=NY, unit='ms') for x in values]
            
            return values[0] if assets_is_scalar else values
        
        else:
            
            log.error('Error in getting spot value: {}'.format(resp.text))
            
            return None
    
    def get_bars(self, assets, data_frequency, bar_count=500):
        raise NotImplementedError('get_bars() not implemented')