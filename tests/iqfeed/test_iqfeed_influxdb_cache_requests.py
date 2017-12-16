import unittest

from pandas.util.testing import assert_frame_equal

from atpy.data.iqfeed.iqfeed_bar_data_provider import *
from atpy.data.iqfeed.iqfeed_influxdb_cache import *
from atpy.data.iqfeed.iqfeed_influxdb_cache_requests import *
from atpy.data.cache.influxdb_cache_requests import *


class TestInfluxDBCacheRequests(unittest.TestCase):
    """
    Test InfluxDBCache
    """

    def setUp(self):
        events.reset()
        events.use_global_event_bus()
        self._client = DataFrameClient('localhost', 8086, 'root', 'root')

        self._client.create_database('test_cache')
        self._client.switch_database('test_cache')

    def tearDown(self):
        self._client.drop_database('test_cache')

    def test_request_ohlc(self):
        with IQFeedHistoryProvider(exclude_nan_ratio=None, num_connections=2) as history, \
                IQFeedInfluxDBCache(use_stream_events=True, client=self._client, history=history, time_delta_back=relativedelta(days=3)) as cache:

            end_prd = datetime.datetime(2017, 5, 1)

            # test single symbol request
            filters = (BarsInPeriodFilter(ticker="IBM", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'),
                       BarsInPeriodFilter(ticker="AAPL", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'),
                       BarsInPeriodFilter(ticker="AAPL", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=600, ascend=True, interval_type='s'))

            adjusted = list()

            for f in filters:
                datum = history.request_data(f, synchronize_timestamps=False, adjust_data=False)
                datum.drop('timestamp', axis=1, inplace=True)
                datum['interval'] = str(f.interval_len) + '_' + f.interval_type
                cache.client.write_points(datum, 'bars', protocol='line', tag_columns=['symbol', 'interval'])
                datum.drop('interval', axis=1, inplace=True)

                datum = history.request_data(f, synchronize_timestamps=False, adjust_data=True)
                adjusted.append(datum)

                cache_requests = IQFeedInfluxDBOHLCRequest(client=self._client, interval_len=f.interval_len, interval_type=f.interval_type, streaming_conn=history.streaming_conn)
                test_data = cache_requests.request(symbol=f.ticker, adjust_data=True)

                assert_frame_equal(datum, test_data)

            for datum, f in zip(adjusted, filters):
                cache_requests = IQFeedInfluxDBOHLCRequest(client=self._client, interval_len=f.interval_len, interval_type=f.interval_type, streaming_conn=history.streaming_conn)
                test_data = cache_requests.request(symbol=f.ticker, adjust_data=True)
                test_data_limit = cache_requests.request(symbol=f.ticker, bgn_prd=f.bgn_prd + relativedelta(days=7), end_prd=f.end_prd - relativedelta(days=7), adjust_data=True)

                self.assertGreater(len(test_data_limit), 0)
                self.assertLess(len(test_data_limit), len(test_data))

            # test multisymbol request
            requested_data = history.request_data(BarsInPeriodFilter(ticker=["AAPL", "IBM"], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'), synchronize_timestamps=False, adjust_data=True)
            cache_requests = IQFeedInfluxDBOHLCRequest(client=self._client, interval_len=3600, streaming_conn=history.streaming_conn)
            test_data = cache_requests.request(symbol=['IBM', 'AAPL', 'TSG'], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, adjust_data=True)
            assert_frame_equal(requested_data, test_data)

            # test any symbol request
            requested_data = history.request_data(BarsInPeriodFilter(ticker=["AAPL", "IBM"], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'), synchronize_timestamps=False, adjust_data=True)

            e = threading.Event()

            @events.listener
            def listen(event):
                if event['type'] == 'cache_result':
                    assert_frame_equal(requested_data, event['data'])
                    e.set()

            cache_requests.on_event({'type': 'request_ohlc', 'data': {'bgn_prd': datetime.datetime(2017, 4, 1), 'end_prd': end_prd, 'adjust_data': True}})

            e.wait()

    def test_request_deltas(self):
        with IQFeedHistoryProvider(exclude_nan_ratio=None, num_connections=2) as history, \
                IQFeedInfluxDBCache(use_stream_events=True, client=self._client, history=history, time_delta_back=relativedelta(days=3)) as cache:
            end_prd = datetime.datetime(2017, 5, 1)

            # test single symbol request
            filters = (BarsInPeriodFilter(ticker="IBM", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'),
                       BarsInPeriodFilter(ticker="AAPL", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'),
                       BarsInPeriodFilter(ticker="AAPL", bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=600, ascend=True, interval_type='s'))

            for f in filters:
                data = history.request_data(f, synchronize_timestamps=False, adjust_data=False)
                data.drop('timestamp', axis=1, inplace=True)
                data['interval'] = str(f.interval_len) + '_' + f.interval_type
                cache.client.write_points(data, 'bars', protocol='line', tag_columns=['symbol', 'interval'])

                delta = (data['close'] - data['open']) / data['open']
                delta = (delta - delta.mean()) / delta.std()

                cache_requests = InfluxDBDeltaAdjustedRequest(client=self._client, interval_len=f.interval_len, interval_type=f.interval_type)
                cache_requests.enable_mean()
                cache_requests.enable_stddev()
                test_delta = cache_requests.request(symbol=f.ticker)['delta']

                np.testing.assert_almost_equal(test_delta.values, delta.values)

            # test multisymbol request
            requested_data = history.request_data(BarsInPeriodFilter(ticker=["AAPL", "IBM"], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'), synchronize_timestamps=False, adjust_data=False)
            delta = (requested_data['close'] - requested_data['open']) / requested_data['open']
            delta = delta.groupby(level=0).apply(lambda x: x - x.mean())
            delta = delta.groupby(level=0).apply(lambda x: x / x.std())

            cache_requests = InfluxDBDeltaAdjustedRequest(client=self._client, interval_len=3600, interval_type='s')
            cache_requests.enable_mean()
            cache_requests.enable_stddev()

            test_delta = cache_requests.request(symbol=['IBM', 'AAPL', 'TSG'], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd)['delta']
            np.testing.assert_almost_equal(test_delta.values, delta.values)

            # test any symbol request
            requested_data = history.request_data(BarsInPeriodFilter(ticker=["AAPL", "IBM"], bgn_prd=datetime.datetime(2017, 4, 1), end_prd=end_prd, interval_len=3600, ascend=True, interval_type='s'), synchronize_timestamps=False, adjust_data=False)
            delta = (requested_data['close'] - requested_data['open']) / requested_data['open']
            delta = delta.groupby(level=0).apply(lambda x: x - x.mean())
            delta = delta.groupby(level=0).apply(lambda x: x / x.std())

            e = threading.Event()

            @events.listener
            def listen(event):
                if event['type'] == 'cache_result':
                    np.testing.assert_almost_equal(test_delta.values, delta.values)
                    e.set()

            cache_requests.on_event({'type': 'request_delta', 'data': {'bgn_prd': datetime.datetime(2017, 4, 1), 'end_prd': end_prd}})

            e.wait()


if __name__ == '__main__':
    unittest.main()