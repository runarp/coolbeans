"""Test Our Matcher Code"""

import unittest
import logging
import yaml

from coolbeans.matcher import Matcher
from beancount.core.data import Transaction, Posting, Amount, D

AMAZON_RULE:dict = None

class TestMatcher(unittest.TestCase):
    def xsetUp(self):
        stream_handler = logging.StreamHandler(sys.stdout)
        logging.getLogger().addHandler(stream_handler)

    def test_validate(self):
        rules = [AMAZON_RULE]
        m = Matcher()
        m.set_rules(rules)

    def test_invalidate(self):
        rules = [{'match-date': r"(?P<order)"}]
        m = Matcher()
        self.assertRaises(
            Exception, m.set_rules, rules
        )

    def test_rule_filter(self):
        expected = {
            'narration': AMAZON_RULE['match-narration'],
            'account': AMAZON_RULE['match-account'],
            'tags': ['household'],
        }
        m = Matcher()
        self.assertEqual(
            m.expand_match_fields(AMAZON_RULE),
            expected
        )

    def x_rule_filter_set(self):
        expected = {
            'transaction': AMAZON_RULE['set-transaction'],
            'posting': AMAZON_RULE['set-posting'],
        }
        m = Matcher()
        for field, expressions in m.rule_filter('set', AMAZON_RULE):
            self.assertEqual(expected[field], expressions)

    def test_match_rule(self):
        narration = "Amazon.com*MA4TS16T0"
        tx = Transaction(
            narration=narration,
            date=None,
            flag=None,
            payee=None,
            tags={},
            links={},
            postings=[],
            meta={'file_name':'', 'lineno':0}
        )
        result = Matcher().match_rule(tx, AMAZON_RULE)
        expected = {
            'narration': {
                'match-parameter': 'narration',
                'match-value': narration,
                'match-group': {
                    'payee': 'Amazon.com',
                    'order_id': 'MA4TS16T0'
                }
            }
        }
        self.assertEqual(result, expected)

    def test_match(self):
        narration = "Amazon.com*MA4TS16T0"
        tx = Transaction(
            narration=narration,
            date=None,
            flag=None,
            payee=None,
            tags={},
            links={},
            postings=[],
            meta={'file_name':'', 'lineno':0}
        )
        m = Matcher([AMAZON_RULE])

        result = m.match(tx)
        self.assertIsInstance(result, dict)

        self.assertEqual(result['rule'], AMAZON_RULE)
        self.assertEqual(result['entry'], tx)

    def test_process_match(self):
        narration = "Amazon.com*MA4TS16T0"
        tx = Transaction(
            narration=narration,
            date=None,
            flag=None,
            payee=None,
            tags={},
            links={},
            postings=[
                Posting(
                    account="Liablities:Card",
                    units=Amount(D(100), "USD"),
                    cost=None,
                    price=None,
                    flag="*",
                    meta={}
                ),
                Posting(
                    account="Expenses:FIXME",
                    units=Amount(D(-100), "USD"),
                    cost=None,
                    price=None,
                    flag="!",
                    meta={}
                )
            ],
            meta={'file_name':'', 'lineno':0}
        )
        m = Matcher([AMAZON_RULE])

        results = m.process([tx])
        self.assertEqual(len(results), 1)
        result = results[0]
        print(yaml.dump(AMAZON_RULE))

AMAZON_RULE = {
    # Match Any
    'match-narration': [
        r"(?P<payee>Amazon.com|amzn mktp us)\*(?P<order_id>.*)",
        r"(?P<payee>Amazon.com)\*(?P<order_id>.*)",
        r"(?P<payee>amzn mktp us)\*(?P<order_id>.*)",
    ],
    # Optional, Match Any
    'match-account': [
        r"Liabilities:.*"
    ],
    'match': {'tags': 'household'},
    'set-transaction': {
        "payee": "Amazon",
        "tags": "kids",
        "meta": {"order-id": "{order_id}"}
    },
    'set-posting': {
        "account": "Expenses:Shopping",
    },
    'test': {
        "Amazon.com*MO7IO3OL2": {
            'order_id': 'MO7IO3OL2'
        },
        "Azure*MO7IO3OL2": {
            'match': False
        },
        "AMZN Mktp US*MA23B5WO1": {
            'order_id': 'MA23B5WO1',
            'payee': 'AMZN Mktp US'
        }
    }
}

if __name__ == '__main__':
    import logging, sys
    import logging

    logger = logging.getLogger(__name__)
    logging.disable(logging.NOTSET)

    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
