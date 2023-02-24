import unittest
import responses
import pandas
import os

from pylivetrader.protocol import Positions
from pylivetrader.backend import tradier
from pylivetrader.assets.assets import Asset
from pylivetrader.finance.order import ORDER_STATUS
from pylivetrader.assets import Equity
import pylivetrader


def dummy_symbol(name):
    return Equity(
        None, None, symbol=name, asset_name=name
    )


#  we can't use the real thing in testing, so we make a fake symbol method
setattr(pylivetrader.api, 'symbol', dummy_symbol)


class TestTradierBackend(unittest.TestCase):
    
    def setUp(self):
        
        self.account = '123456789'
        self.url = 'api.tradier.com'
        self.version = 'v1'
        self.bearer = 'fake-token'
        
        os.environ['APCA_API_BASE_URL'] = 'https://paper-api.alpaca.markets'
        os.environ['APCA_API_KEY_ID'] = 'PKZTU1GD0OK44EQKPKQS'
        os.environ['APCA_API_SECRET_KEY'] = (
            'Dd0iMUxNx/MKonnzSLlZul0ljgsx8m22NnsVjgQN'
        )
        
        self.broker = tradier.Backend(
            url='api.tradier.com',
            version='v1',
            account='123456789',
            bearer=self.bearer
        )
        
    @responses.activate
    def test_get_single_position(self):
        """Retrieve the current position"""
        
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/positions'),
            json={
                'positions': {
                    'position': {
                        'cost_basis': 5000.232,
                        'date_acquired': '2014-04-28T13:51:26.800Z',
                        'id': 1,
                        'quantity': 500,
                        'symbol': 'A'
                    }
                }
            }
        )
        
        positions = self.broker.positions
        
        #  TODO: need to create Equity/Asset objects
        
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions['A'].last_sale_price, 0)
        self.assertIsNone(positions['A'].last_sale_date)
        self.assertEqual(positions['A'].amount, 500)
        self.assertEqual(positions['A'].cost_basis, 10.000464)
        self.assertEqual(positions['A'].sid, 'A')
        
    @responses.activate
    def test_get_multiple_positions(self):
        """Retrieve the current positions"""
    
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/positions'),
            json={
                'positions': {
                    'position': [
                        {
                            'cost_basis': 5000.232,
                            'date_acquired': '2014-04-28T13:51:26.800Z',
                            'id': 1,
                            'quantity': 500,
                            'symbol': 'A'
                        },
                        {
                            'cost_basis': 3004.56,
                            'date_acquired': '2014-04-28T13:51:26.800Z',
                            'id': 2,
                            'quantity': 300,
                            'symbol': 'B'
                        }
                    ]
                }
            }
        )
    
        positions = self.broker.positions
    
        #  TODO: need to create Equity/Asset objects
    
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions['A'].last_sale_price, 0)
        self.assertIsNone(positions['A'].last_sale_date)
        self.assertEqual(positions['A'].amount, 500)
        self.assertEqual(positions['A'].cost_basis, 10.000464)
        self.assertEqual(positions['A'].sid, 'A')
        
    @responses.activate
    def test_null_positions(self):
        """Retrieve empty positions, i.e. Null"""
    
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/positions'),
            json={
                'positions': 'null'
            }
        )
    
        positions = self.broker.positions
    
        #  TODO: need to create Equity/Asset objects
    
        self.assertEqual(len(positions), 0)
        
    @responses.activate
    def test_get_portfolio(self):
        """Retrieve portfolio still with unsettled cash"""

        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/balances'),
            json={
                'balances': {
                    'option_short_value': 0,
                    'total_equity': 1987.2056,
                    'account_number': '6YA05267',
                    'account_type': 'cash',
                    'close_pl': -0.6344,
                    'current_requirement': 0,
                    'equity': 0,
                    'long_market_value': 0,
                    'market_value': 0,
                    'open_pl': 0,
                    'option_long_value': 0,
                    'option_requirement': 0,
                    'pending_orders_count': 0,
                    'short_market_value': 0,
                    'stock_long_value': 0,
                    'total_cash': 1987.2056,
                    'uncleared_funds': 0,
                    'pending_cash': 0,
                    'cash': {
                        'cash_available': 1482.1705,
                        'sweep': 0,
                        'unsettled_funds': 505.0351
                    }
                }
            }
        )
        
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/positions'),
            json={
                'positions': 'null'
            }
        )
        
        portfolio = self.broker.portfolio
        
        self.assertEqual(portfolio.capital_used, 0)
        self.assertEqual(portfolio.starting_cash, 0)
        self.assertEqual(portfolio.portfolio_value, 1987.2056)
        self.assertEqual(portfolio.pnl, 0)
        self.assertEqual(portfolio.returns, 0)
        self.assertEqual(portfolio.cash, 1987.2056)
        self.assertIsInstance(portfolio.positions, Positions)
        self.assertIsNone(portfolio.start_date)
        self.assertEqual(portfolio.positions_value, 0)
        
    @responses.activate
    def test_get_portfolio_with_open_positions(self):
        """Retrieve portfolio still with open positions"""
    
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/balances'),
            json={
                'balances': {
                    'option_short_value': 0,
                    'total_equity': 1994.8905,
                    'account_number': '6YA05267',
                    'account_type': 'cash',
                    'close_pl': 0,
                    'current_requirement': 0,
                    'equity': 0,
                    'long_market_value': 505.74,
                    'market_value': 505.74,
                    'open_pl': 0.0705,
                    'option_long_value': 0,
                    'option_requirement': 0,
                    'pending_orders_count': 0,
                    'short_market_value': 0,
                    'stock_long_value': 505.74,
                    'total_cash': 1489.1505,
                    'uncleared_funds': 0,
                    'pending_cash': 0,
                    'cash': {
                        'cash_available': 1489.1505,
                        'sweep': 0,
                        'unsettled_funds': 0
                    }
                }
            }
        )
        
        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/positions'),
            json={
                'positions': {
                    'position': [
                        {
                            'cost_basis': 110.42,
                            'date_acquired': '2014-04-28T13:51:26.800Z',
                            'id': 1,
                            'quantity': 2,
                            'symbol': 'A'
                        },
                        {
                            'cost_basis': 395.24,
                            'date_acquired': '2014-04-28T13:51:26.800Z',
                            'id': 2,
                            'quantity': 5,
                            'symbol': 'B'
                        }
                    ]
                }
            }
        )
    
        portfolio = self.broker.portfolio
    
        self.assertEqual(portfolio.capital_used, 0)
        self.assertEqual(portfolio.starting_cash, 0)
        self.assertEqual(portfolio.portfolio_value, 1994.8905)
        self.assertEqual(portfolio.pnl, 0)
        self.assertEqual(portfolio.returns, 0)
        self.assertEqual(portfolio.cash, 1489.1505)
        self.assertIsInstance(portfolio.positions, Positions)
        self.assertEqual(len(portfolio.positions), 2)
        self.assertEqual(portfolio.start_date, None)
        self.assertEqual(portfolio.positions_value, 505.74)

    @responses.activate
    def test_get_account(self):
        """Basic fetch of the account"""

        responses.add(
            responses.GET,
            self.broker._form_url('/accounts/[[account]]/balances'),
            json={
                'balances': {
                    'option_short_value': 0,
                    'total_equity': 1987.2056,
                    'account_number': '6YA05267',
                    'account_type': 'cash',
                    'close_pl': -0.6344,
                    'current_requirement': 0,
                    'equity': 0,
                    'long_market_value': 0,
                    'market_value': 0,
                    'open_pl': 0,
                    'option_long_value': 0,
                    'option_requirement': 0,
                    'pending_orders_count': 0,
                    'short_market_value': 0,
                    'stock_long_value': 0,
                    'total_cash': 1987.2056,
                    'uncleared_funds': 0,
                    'pending_cash': 0,
                    'cash': {
                        'cash_available': 1482.1705,
                        'sweep': 0,
                        'unsettled_funds': 505.0351
                    }
                }
            }
        )
        
        account = self.broker.account
        
        self.assertEqual(account.settled_cash, 1482.1705)
        self.assertEqual(account.accrued_interest, 0)
        self.assertEqual(account.buying_power, 1987.2056)
        self.assertEqual(account.equity_with_loan, 0)
        self.assertEqual(account.total_positions_value, 0)
        self.assertEqual(account.total_positions_exposure, 0)
        self.assertEqual(account.regt_equity, 0)
        self.assertEqual(account.regt_margin, float('inf'))
        self.assertEqual(account.initial_margin_requirement, 0)
        self.assertEqual(account.maintenance_margin_requirement, 0)
        self.assertEqual(account.available_funds, 1482.1705)
        self.assertEqual(account.excess_liquidity, 0)
        self.assertEqual(account.cushion, 0)
        self.assertEqual(account.day_trades_remaining, float('inf'))
        self.assertEqual(account.leverage, 0)
        self.assertEqual(account.net_leverage, 0)
        self.assertEqual(account.net_liquidation, 1987.2056)

    @responses.activate
    def test_get_spot_value_single(self):
        """Basic single spot value"""
        
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={}'.format('AMD')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': {
                        'symbol': 'AMD',
                        'description': 'Advanced Micro Devices Inc',
                        'exch': 'Q',
                        'type': 'stock',
                        'last': 26.44,
                        'change': 0.09,
                        'volume': 39835788,
                        'open': 26.61,
                        'high': 26.925,
                        'low': 26.4,
                        'close': 26.44,
                        'bid': 26.41,
                        'ask': 26.44,
                        'change_percentage': 0.31,
                        'average_volume': 66916016,
                        'last_volume': 469561,
                        'trade_date': 1558728000000,
                        'prevclose': 26.36,
                        'week_52_high': 34.14,
                        'week_52_low': 13.03,
                        'bidsize': 10,
                        'bidexch': 'P',
                        'bid_date': 1558742395000,
                        'asksize': 210,
                        'askexch': 'K',
                        'ask_date': 1558742336000,
                        'root_symbols': 'AMD'
                    }
                }
            }
        )
        
        amd = Asset(
            sid='0C0000099E',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        spot_value = self.broker.get_spot_value(amd, 'price', None, 'daily')

        self.assertEqual(spot_value, 26.44)
        
    @responses.activate
    def test_get_spot_value_multiple(self):
        """Basic spot values"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={},{}'.format('AMD', 'ODP')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': [
                        {
                            'symbol': 'AMD',
                            'description': 'Advanced Micro Devices Inc',
                            'exch': 'Q',
                            'type': 'stock',
                            'last': 26.44,
                            'change': 0.09,
                            'volume': 39835788,
                            'open': 26.61,
                            'high': 26.925,
                            'low': 26.4,
                            'close': 26.44,
                            'bid': 26.41,
                            'ask': 26.44,
                            'change_percentage': 0.31,
                            'average_volume': 66916016,
                            'last_volume': 469561,
                            'trade_date': 1558728000000,
                            'prevclose': 26.36,
                            'week_52_high': 34.14,
                            'week_52_low': 13.03,
                            'bidsize': 10,
                            'bidexch': 'P',
                            'bid_date': 1558742395000,
                            'asksize': 210,
                            'askexch': 'K',
                            'ask_date': 1558742336000,
                            'root_symbols': 'AMD'
                        },
                        {
                            'symbol': 'ODP',
                            'description': 'Office Depot',
                            'exch': 'N',
                            'type': 'stock',
                            'last': 21.44,
                            'change': 0.09,
                            'volume': 39835788,
                            'open': 21.61,
                            'high': 21.925,
                            'low': 21.4,
                            'close': 21.44,
                            'bid': 21.41,
                            'ask': 21.44,
                            'change_percentage': 0.31,
                            'average_volume': 66916016,
                            'last_volume': 469561,
                            'trade_date': 1558728000000,
                            'prevclose': 26.36,
                            'week_52_high': 34.14,
                            'week_52_low': 13.03,
                            'bidsize': 10,
                            'bidexch': 'P',
                            'bid_date': 1558742395000,
                            'asksize': 210,
                            'askexch': 'K',
                            'ask_date': 1558742336000,
                            'root_symbols': 'ODP'
                        }
                    ]
                }
            }
        )
    
        amd = Asset(
            sid='amd',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        odp = Asset(
            sid='odp',
            exchange='NYSE',
            symbol='ODP',
            asset_name='Office Depot',
        )
        spot_values = self.broker.get_spot_value(
            [amd, odp], 'price', None, 'daily')
    
        self.assertEqual(len(spot_values), 2)
        self.assertEqual(spot_values[0], 26.44)
        self.assertEqual(spot_values[1], 21.44)
        
    @responses.activate
    def test_get_spot_value_single_close(self):
        """Basic single spot value"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={}'.format('AMD')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': {
                        'symbol': 'AMD',
                        'description': 'Advanced Micro Devices Inc',
                        'exch': 'Q',
                        'type': 'stock',
                        'last': 26.44,
                        'change': 0.09,
                        'volume': 39835788,
                        'open': 26.61,
                        'high': 26.925,
                        'low': 26.4,
                        'close': 26.44,
                        'bid': 26.41,
                        'ask': 26.44,
                        'change_percentage': 0.31,
                        'average_volume': 66916016,
                        'last_volume': 469561,
                        'trade_date': 1558728000000,
                        'prevclose': 26.36,
                        'week_52_high': 34.14,
                        'week_52_low': 13.03,
                        'bidsize': 10,
                        'bidexch': 'P',
                        'bid_date': 1558742395000,
                        'asksize': 210,
                        'askexch': 'K',
                        'ask_date': 1558742336000,
                        'root_symbols': 'AMD'
                    }
                }
            }
        )
    
        amd = Asset(
            sid='0C0000099E',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        spot_value = self.broker.get_spot_value(amd, 'close', None, 'daily')
    
        self.assertEqual(spot_value, 26.44)
        
    @responses.activate
    def test_get_spot_value_single_open(self):
        """Basic single spot value"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={}'.format('AMD')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': {
                        'symbol': 'AMD',
                        'description': 'Advanced Micro Devices Inc',
                        'exch': 'Q',
                        'type': 'stock',
                        'last': 26.44,
                        'change': 0.09,
                        'volume': 39835788,
                        'open': 26.61,
                        'high': 26.925,
                        'low': 26.4,
                        'close': 26.44,
                        'bid': 26.41,
                        'ask': 26.44,
                        'change_percentage': 0.31,
                        'average_volume': 66916016,
                        'last_volume': 469561,
                        'trade_date': 1558728000000,
                        'prevclose': 26.36,
                        'week_52_high': 34.14,
                        'week_52_low': 13.03,
                        'bidsize': 10,
                        'bidexch': 'P',
                        'bid_date': 1558742395000,
                        'asksize': 210,
                        'askexch': 'K',
                        'ask_date': 1558742336000,
                        'root_symbols': 'AMD'
                    }
                }
            }
        )
    
        amd = Asset(
            sid='0C0000099E',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        spot_value = self.broker.get_spot_value(amd, 'open', None, 'daily')
    
        self.assertEqual(spot_value, 26.61)
        
    @responses.activate
    def test_get_spot_value_single_last_traded(self):
        """Basic single spot value"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={}'.format('AMD')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': {
                        'symbol': 'AMD',
                        'description': 'Advanced Micro Devices Inc',
                        'exch': 'Q',
                        'type': 'stock',
                        'last': 26.44,
                        'change': 0.09,
                        'volume': 39835788,
                        'open': 26.61,
                        'high': 26.925,
                        'low': 26.4,
                        'close': 26.44,
                        'bid': 26.41,
                        'ask': 26.44,
                        'change_percentage': 0.31,
                        'average_volume': 66916016,
                        'last_volume': 469561,
                        'trade_date': 1558728000000,
                        'prevclose': 26.36,
                        'week_52_high': 34.14,
                        'week_52_low': 13.03,
                        'bidsize': 10,
                        'bidexch': 'P',
                        'bid_date': 1558742395000,
                        'asksize': 210,
                        'askexch': 'K',
                        'ask_date': 1558742336000,
                        'root_symbols': 'AMD'
                    }
                }
            }
        )
    
        amd = Asset(
            sid='0C0000099E',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        spot_value = self.broker.get_spot_value(
            amd, 'last_traded', None, 'daily')
    
        self.assertEqual(
            spot_value,
            pandas.Timestamp(1558728000000, tz=tradier.NY, unit='ms')
        )

    @responses.activate
    def test_get_last_traded_dt_basic(self):
        """Simple fetch of last traded pandas timestamp for an asset"""

        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/markets/quotes?symbols={}'.format('AMD')
            ),
            match_querystring=True,
            json={
                'quotes': {
                    'quote': {
                        'symbol': 'AMD',
                        'description': 'Advanced Micro Devices Inc',
                        'exch': 'Q',
                        'type': 'stock',
                        'last': 26.44,
                        'change': 0.09,
                        'volume': 39835788,
                        'open': 26.61,
                        'high': 26.925,
                        'low': 26.4,
                        'close': 26.44,
                        'bid': 26.41,
                        'ask': 26.44,
                        'change_percentage': 0.31,
                        'average_volume': 66916016,
                        'last_volume': 469561,
                        'trade_date': 1558728000000,
                        'prevclose': 26.36,
                        'week_52_high': 34.14,
                        'week_52_low': 13.03,
                        'bidsize': 10,
                        'bidexch': 'P',
                        'bid_date': 1558742395000,
                        'asksize': 210,
                        'askexch': 'K',
                        'ask_date': 1558742336000,
                        'root_symbols': 'AMD'
                    }
                }
            }
        )

        amd = Asset(
            sid='0C0000099E',
            exchange='NASDAQ',
            symbol='AMD',
            asset_name='Advanced Micro Devices Inc',
        )
        spot_value = self.broker.get_last_traded_dt(amd)

        self.assertEqual(
            spot_value,
            pandas.Timestamp(1558728000000, tz=tradier.NY, unit='ms')
        )
        
    @responses.activate
    def test_get_order_filled(self):
        """Retrieve a single order"""

        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/accounts/[[account]]/orders/{id}'.format(id=228176)
            ),
            json={
                'order': {
                    'id': 228176,
                    'type': 'market',
                    'symbol': 'AAPL',
                    'side': 'buy',
                    'quantity': 50.00000000,
                    'status': 'filled',
                    'duration': 'pre',
                    'avg_fill_price': 187.93000000,
                    'exec_quantity': 50.00000000,
                    'last_fill_price': 187.93000000,
                    'last_fill_quantity': 50.00000000,
                    'remaining_quantity': 0.00000000,
                    'create_date': '2018-06-01T12:02:37.377Z',
                    'transaction_date': '2018-06-01T13:45:13.340Z',
                    'class': 'equity'
                }
            }
        )
        
        order = self.broker.get_order(228176)
        
        dt = pandas.Timestamp('2018-06-01T12:02:37.377Z')
        self.assertEqual('AAPL', order.asset.symbol)
        self.assertEqual(50, order.amount)
        self.assertEqual(None, order.stop)
        self.assertEqual(None, order.limit)
        self.assertEqual(dt, order.dt)
        self.assertEqual(3.49, order.commission)
        self.assertEqual(ORDER_STATUS.FILLED, order.status)
        self.assertEqual(50, order.filled)
        self.assertEqual(228176, order.id)

    @responses.activate
    def test_get_order_open(self):
        """Retrieve a single open order"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/accounts/[[account]]/orders/{id}'.format(id=228176)
            ),
            json={
                'order': {
                    'id': 228176,
                    'type': 'market',
                    'symbol': 'AAPL',
                    'side': 'buy',
                    'quantity': 50.00000000,
                    'status': 'open',
                    'duration': 'pre',
                    'avg_fill_price': 0.00,
                    'exec_quantity': 0.00,
                    'last_fill_price': 0.00,
                    'last_fill_quantity': 0.00,
                    'remaining_quantity': 50.000000,
                    'create_date': '2018-06-01T12:02:37.377Z',
                    'transaction_date': '2018-06-01T13:45:13.340Z',
                    'class': 'equity'
                }
            }
        )
    
        order = self.broker.get_order(228176)
    
        dt = pandas.Timestamp('2018-06-01T12:02:37.377Z')
        self.assertEqual('AAPL', order.asset.symbol)
        self.assertEqual(50, order.amount)
        self.assertEqual(None, order.stop)
        self.assertEqual(None, order.limit)
        self.assertEqual(dt, order.dt)
        self.assertEqual(3.49, order.commission)
        self.assertEqual(ORDER_STATUS.OPEN, order.status)
        self.assertEqual(0, order.filled)
        self.assertEqual(228176, order.id)

    @responses.activate
    def test_get_order_filled_sell(self):
        """Retrieve a single sell side order"""
    
        responses.add(
            responses.GET,
            url=self.broker._form_url(
                '/accounts/[[account]]/orders/{id}'.format(id=228176)
            ),
            json={
                'order': {
                    'id': 228176,
                    'type': 'market',
                    'symbol': 'AAPL',
                    'side': 'sell',
                    'quantity': 50.00000000,
                    'status': 'filled',
                    'duration': 'pre',
                    'avg_fill_price': 187.93000000,
                    'exec_quantity': 50.00000000,
                    'last_fill_price': 187.93000000,
                    'last_fill_quantity': 50.00000000,
                    'remaining_quantity': 0.00000000,
                    'create_date': '2018-06-01T12:02:37.377Z',
                    'transaction_date': '2018-06-01T13:45:13.340Z',
                    'class': 'equity'
                }
            }
        )
    
        order = self.broker.get_order(228176)
    
        dt = pandas.Timestamp('2018-06-01T12:02:37.377Z')
        self.assertEqual('AAPL', order.asset.symbol)
        self.assertEqual(-50, order.amount)
        self.assertEqual(None, order.stop)
        self.assertEqual(None, order.limit)
        self.assertEqual(dt, order.dt)
        self.assertEqual(3.49, order.commission)
        self.assertEqual(ORDER_STATUS.FILLED, order.status)
        self.assertEqual(50, order.filled)
        self.assertEqual(228176, order.id)
        
    @responses.activate
    def test_all_orders_open(self):
        """Test getting all orders"""

        responses.add(
            responses.GET,
            url=self.broker._form_url('/accounts/[[account]]/orders'),
            json={
                
                'order': {
                    'id': 228176,
                    'type': 'market',
                    'symbol': 'AAPL',
                    'side': 'sell',
                    'quantity': 50.00000000,
                    'status': 'filled',
                    'duration': 'pre',
                    'avg_fill_price': 187.93000000,
                    'exec_quantity': 50.00000000,
                    'last_fill_price': 187.93000000,
                    'last_fill_quantity': 50.00000000,
                    'remaining_quantity': 0.00000000,
                    'create_date': '2018-06-01T12:02:37.377Z',
                    'transaction_date': '2018-06-01T13:45:13.340Z',
                    'class': 'equity'
                }
            }
        )
        
        self.broker.all_orders()
