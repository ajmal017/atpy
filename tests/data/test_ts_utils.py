import logging
import random
import unittest

import atpy.data.tradingcalendar as tcal
from atpy.backtesting.data_replay import DataReplay
from atpy.data.iqfeed.iqfeed_history_provider import *
from atpy.data.ts_util import current_period
from atpy.data.ts_util import set_periods


class TestTSUtils(unittest.TestCase):

    def test_set_periods(self):
        batch_len = 1000

        with IQFeedHistoryProvider() as provider:
            # One symbol, all periods
            df = provider.request_data(BarsFilter(ticker="AAPL", interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False)

            set_periods(df)
            self.assertTrue('period' in df.columns)
            self.assertEqual(len(pd.unique(df['period'].dropna())), 2)
            self.assertEqual(len(df['period'].dropna()), len(df['period']))

            # Multiple symbols, all periods
            df = provider.request_data(BarsFilter(ticker=["AAPL", "IBM"], interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False).swaplevel(0, 1).sort_index()

            set_periods(df)
            self.assertTrue('period' in df.columns)
            self.assertEqual(len(pd.unique(df['period'].dropna())), 2)
            self.assertEqual(len(df['period'].dropna()), len(df['period']))

            # Multiple symbols, N periods
            df = provider.request_data(BarsFilter(ticker=["AAPL", "IBM"], interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False).swaplevel(0, 1).sort_index()
            lc = tcal.open_and_closes.loc[min(df['timestamp']): max(df['timestamp'])].iloc[::-1]
            xs = pd.IndexSlice
            df = df.loc[xs[:lc.iloc[0]['market_close'], :]].iloc[:-3]
            set_periods(df)
            self.assertTrue('period' in df.columns)
            self.assertEqual(len(pd.unique(df['period'].dropna())), 2)
            self.assertEqual(len(df['period'].dropna()), len(df['period']))

    def test_set_periods_performance(self):
        logging.basicConfig(level=logging.DEBUG)

        batch_len = 10000
        batch_width = 1000

        with IQFeedHistoryProvider() as provider:
            df = provider.request_data(BarsFilter(ticker="AAPL", interval_len=60, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False)

            dfs = {'AAPL': df}
            for i in range(batch_width):
                dfs['AAPL_' + str(i)] = df.sample(random.randint(int(len(df) / 3), len(df) - 1))

            dfs = pd.concat(dfs).swaplevel(0, 1).sort_index()

            now = datetime.datetime.now()
            set_periods(dfs)
            logging.getLogger(__name__).debug('Time elapsed ' + str(datetime.datetime.now() - now) + ' for ' + str(batch_len) + ' steps; ' + str(batch_width) + ' width')

    def test_current_period(self):
        batch_len = 1000

        with IQFeedHistoryProvider() as provider:
            # One symbol, all periods
            df = provider.request_data(BarsFilter(ticker="AAPL", interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False)

            slc, period = current_period(df)
            self.assertTrue(period in ('trading-hours', 'after-hours'))
            self.assertGreater(len(df), len(slc))

            # Multiple symbols, all periods
            df = provider.request_data(BarsFilter(ticker=["AAPL", "IBM"], interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False).swaplevel(0, 1).sort_index()

            slc, period = current_period(df)
            self.assertTrue(period in ('trading-hours', 'after-hours'))
            self.assertGreater(len(df), len(slc))

            df = provider.request_data(BarsFilter(ticker=["AAPL", "IBM"], interval_len=300, interval_type='s', max_bars=batch_len), sync_timestamps=False, adjust_data=False).swaplevel(0, 1).sort_index()
            lc = tcal.open_and_closes.loc[min(df['timestamp']): max(df['timestamp'])].iloc[::-1]
            xs = pd.IndexSlice
            df = df.loc[xs[:lc.iloc[0]['market_close'], :]].iloc[:-3]

            slc, period = current_period(df)
            self.assertTrue(period in ('trading-hours', 'after-hours'))
            self.assertGreater(len(df), len(slc))

    def test_current_period_2(self):
        logging.basicConfig(level=logging.DEBUG)

        batch_len = 10000
        batch_width = 2000

        l1, l2 = list(), list()
        with IQFeedHistoryProvider() as provider, DataReplay().add_source(iter(l1), 'e1', historical_depth=1000) as dr:
            now = datetime.datetime.now()
            df = provider.request_data(BarsFilter(ticker="AAPL", interval_len=60, interval_type='s', max_bars=batch_len), adjust_data=False, sync_timestamps=False)

            dfs1 = {'AAPL': df}
            for i in range(batch_width):
                dfs1['AAPL_' + str(i)] = df.sample(random.randint(int(len(df) / 3), len(df) - 1))

            df = pd.concat(dfs1).swaplevel(0, 1)
            df.reset_index(level=1, inplace=True)
            df.sort_index(inplace=True)
            df.set_index('level_1', drop=False, append=True, inplace=True)
            l1.append(df)

            logging.getLogger(__name__).debug('Random data generated in ' + str(datetime.datetime.now() - now) + ' with shapes ' + str(df.shape))

            now = datetime.datetime.now()

            for i, r in enumerate(dr):
                if i % 1000 == 0 and i > 0:
                    new_now = datetime.datetime.now()
                    elapsed = new_now - now
                    logging.getLogger(__name__).debug('Time elapsed ' + str(elapsed) + ' for ' + str(i) + ' iterations; ' + str(elapsed / 1000) + ' per iteration')
                    self.assertGreater(10000, (elapsed / 1000).microseconds)
                    now = new_now

                for e in r:
                    period, _ = current_period(r[e])
                    if len(period) >= len(r[e]):
                        data, period = current_period(r[e])
                        self.assertTrue(not data.empty)
                        self.assertTrue(period in ('trading-hours', 'after-hours'))

            elapsed = datetime.datetime.now() - now
            logging.getLogger(__name__).debug('Time elapsed ' + str(elapsed) + ' for ' + str(i + 1) + ' iterations; ' + str(elapsed / (i % 1000)) + ' per iteration')