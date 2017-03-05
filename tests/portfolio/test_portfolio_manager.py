import unittest
from atpy.portfolio.portfolio_manager import *
from pyevents_util.mongodb.mongodb_store import *
from atpy.data.iqfeed.iqfeed_level_1_provider import *


class TestPortfolioManager(unittest.TestCase):
    """
    Test portfolio manager
    """

    def setUp(self):
        events.reset()

    def test_1(self):
        pm = PortfolioManager(10000)

        # order 1
        o2 = MarketOrder(Type.BUY, 'GOOG', 100)
        o2.add_position(14, 23)
        o2.add_position(86, 24)
        o2.fulfill_time = datetime.datetime.now()

        e1 = threading.Event()
        pm.add_order += lambda x: e1.set()
        pm.on_event({'type': 'order_fulfilled', 'order': o2})
        e1.wait()

        self.assertEqual(len(pm.quantity()), 1)
        self.assertEqual(pm.quantity()['GOOG'], 100)
        self.assertEqual(pm.quantity('GOOG'), 100)
        self.assertEqual(pm.value('GOOG', multiply_by_quantity=True), 100 * 24)
        self.assertEqual(len(pm.value()), 1)
        self.assertEqual(pm.value(multiply_by_quantity=True)['GOOG'], 100 * 24)
        self.assertEqual(pm.capital, 10000 - (14 * 23 + 86 * 24))

        # order 2
        o2 = MarketOrder(Type.BUY, 'GOOG', 150)
        o2.add_position(110, 25)
        o2.add_position(30, 26)
        o2.add_position(10, 27)
        o2.fulfill_time = datetime.datetime.now()

        e2 = threading.Event()
        pm.add_order += lambda x: e2.set()
        pm.on_event({'type': 'order_fulfilled', 'order': o2})
        e2.wait()

        self.assertEqual(len(pm.quantity()), 1)
        self.assertEqual(pm.quantity()['GOOG'], 250)
        self.assertEqual(pm.quantity('GOOG'), 250)
        self.assertEqual(pm.value('GOOG', multiply_by_quantity=True), 250 * 27)
        self.assertEqual(len(pm.value()), 1)
        self.assertEqual(pm.value(multiply_by_quantity=True)['GOOG'], 250 * 27)
        self.assertEqual(pm.capital, 10000 - (14 * 23 + 86 * 24 + 110 * 25 + 30 * 26 + 10 * 27))

        # order 3
        o3 = MarketOrder(Type.SELL, 'GOOG', 60)
        o3.add_position(60, 22)
        o3.fulfill_time = datetime.datetime.now()

        e3 = threading.Event()
        pm.add_order += lambda x: e3.set()
        pm.on_event({'type': 'order_fulfilled', 'order': o3})
        e3.wait()

        self.assertEqual(len(pm.quantity()), 1)
        self.assertEqual(pm.quantity()['GOOG'], 190)
        self.assertEqual(pm.quantity('GOOG'), 190)
        self.assertEqual(pm.value('GOOG'), 22)
        self.assertEqual(len(pm.value()), 1)
        self.assertEqual(pm.value()['GOOG'], 22)
        self.assertEqual(pm.capital, 10000 - (14 * 23 + 86 * 24 + 110 * 25 + 30 * 26 + 10 * 27) + 60 * 22)

        # order 4
        o4 = MarketOrder(Type.BUY, 'AAPL', 50)
        o4.add_position(50, 21)
        o4.fulfill_time = datetime.datetime.now()

        e4 = threading.Event()
        pm.add_order += lambda x: e4.set()
        pm.on_event({'type': 'order_fulfilled', 'order': o4})
        e4.wait()

        self.assertEqual(len(pm.quantity()), 2)
        self.assertEqual(pm.quantity()['AAPL'], 50)
        self.assertEqual(pm.quantity('AAPL'), 50)
        self.assertEqual(pm.value('AAPL', multiply_by_quantity=True), 50 * 21)
        self.assertEqual(len(pm.value()), 2)
        self.assertEqual(pm.value(multiply_by_quantity=True)['AAPL'], 50 * 21)
        self.assertEqual(pm.capital, 10000 - (14 * 23 + 86 * 24 + 110 * 25 + 30 * 26 + 10 * 27 + 50 * 21) + 60 * 22)

    def test_logging(self):
        events.use_global_event_bus()

        client = pymongo.MongoClient()

        try:
            # logging.basicConfig(level=logging.DEBUG)

            events.use_global_event_bus()

            pm = PortfolioManager(10000)

            store = MongoDBStore(client.test_db.store, lambda event: event['type'] == 'portfolio_update')

            # order 1
            o1 = MarketOrder(Type.BUY, 'GOOG', 100)
            o1.add_position(14, 23)
            o1.add_position(86, 24)
            o1.fulfill_time = datetime.datetime.now()

            e1 = threading.Event()
            events.listener(lambda x: e1.set() if x['type'] == 'store_object' else None)
            pm.on_event({'type': 'order_fulfilled', 'order': o1})
            e1.wait()

            # order 2
            o2 = MarketOrder(Type.BUY, 'AAPL', 50)
            o2.add_position(50, 21)
            o2.fulfill_time = datetime.datetime.now()

            e2 = threading.Event()
            events.listener(lambda x: e2.set() if x['type'] == 'store_object' else None)
            pm.on_event({'type': 'order_fulfilled', 'order': o2})
            e2.wait()

            obj = store.restore(client.test_db.store, pm._id)
            self.assertEqual(obj._id, pm._id)
            self.assertEqual(len(obj.orders), 2)
            self.assertEqual(obj.initial_capital, 10000)
        finally:
            client.drop_database('test_db')

    def test_price_updates(self):
        events.use_global_event_bus()

        with IQFeedLevel1Listener(minibatch=2):
            pm = PortfolioManager(10000)

            # order 1
            o1 = MarketOrder(Type.BUY, 'GOOG', 100)
            o1.add_position(14, 1)
            o1.add_position(86, 1)
            o1.fulfill_time = datetime.datetime.now()

            e1 = threading.Event()
            events.listener(lambda x: e1.set() if x['type'] == 'portfolio_value_update' else None)
            pm.on_event({'type': 'order_fulfilled', 'order': o1})
            e1.wait()

            self.assertNotEquals(pm.value('GOOG'), 1)

            # order 2
            o2 = MarketOrder(Type.BUY, 'GOOG', 90)
            o2.add_position(4, 0.5)
            o2.add_position(86, 0.5)
            o2.fulfill_time = datetime.datetime.now()

            self.assertNotEquals(pm.value('GOOG'), 1)
            self.assertNotEquals(pm.value('GOOG'), 0.5)

            # order 3
            o3 = MarketOrder(Type.BUY, 'AAPL', 100)
            o3.add_position(14, 0.2)
            o3.add_position(86, 0.2)
            o3.fulfill_time = datetime.datetime.now()

            e3 = threading.Event()
            events.listener(lambda x: e3.set() if x['type'] == 'portfolio_value_update' else None)
            pm.on_event({'type': 'order_fulfilled', 'order': o3})
            e3.wait()

            self.assertNotEquals(pm.value('GOOG'), 1)
            self.assertNotEquals(pm.value('GOOG'), 0.5)
            self.assertNotEquals(pm.value('AAPL'), 0.2)
            self.assertEqual(len(pm._values), 2)

if __name__ == '__main__':
    unittest.main()
