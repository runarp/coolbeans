import re
import yaml
import unittest
import logging

from beancount.parser import parser

from coolbeans.rule import KEY_RE, Rule, MatchRule
from coolbeans import matcher


logger = logging.getLogger(__name__)


class TestMatches(unittest.TestCase):

    def match_any(self, regex_list, value, expected_groupdict):

        match = None
        regex = None
        for regex in regex_list:
            match = regex.fullmatch(value)
            if match:
                break

        if not match:
            self.assertIs(expected_groupdict, None, f"{value} !! {regex}")
        else:
            self.assertEqual(expected_groupdict, match.groupdict(), f"{value} !! {regex}")

    def test_match_re_1(self):
        self.match_any(KEY_RE, "miss", None)
        self.match_any(KEY_RE, "match", {})

    def test_match_re_3(self):
        self.match_any(MATCH_KEY_RE, "match-narration", {'parameter': 'narration'})

    def test_match_re_2(self):
        self.match_any(
            MATCH_KEY_RE,
            "match-transaction-narration",
            {'parameter': 'narration', 'directive': 'transaction'}
        )

    def test_match_re_meta(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1", {
            'parameter': 'meta',
            'directive': 'tx',
            'meta': 'custom1'
        })

    def test_match_re_meta_with_dash(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1-field", {
            'parameter': 'meta',
            'directive': 'tx',
            'meta': 'custom1-field'
        })

    def test_match_re_meta_with_dash_no_entity(self):
        self.match_any(MATCH_KEY_RE, "match-meta-custom1-field", {
            'parameter': 'meta',
            'directive': None,
            'meta': 'custom1-field'
        })

    def test_require_full(self):
        self.match_any(MATCH_KEY_RE, "XXXmatch-meta-custom1-field", None)

    def test_require_full2(self):
        self.match_any(MATCH_KEY_RE, "match__", None)

    def test_compile_basic(self):
        """Expand a Rule into actionable steps"""

        rule = yaml.load("""
        match:
            narration: AirBnB(.*)
        """, Loader=yaml.FullLoader)

        r = Rule(rule)

        expected_rule = MatchRule(
            directive='transaction',
            parameter='narration',
            meta_key=None,
            regular_expressions={
                re.compile("AirBnB(.*)")
            }
        )

        self.assertEqual(
            {'transaction-narration': expected_rule},
            r.match_requirements
        )

    def test_compile_nested(self):
        """Expand a Rule into actionable steps"""

        rule = yaml.load("""
        match:
            narration: AirBnB(.*)
        match-narration:
            - Air BnB(.*)
            - BnB Payments(.*)
        set-account: Income:AirBnB
        set-tags: passive-income
        """, Loader=yaml.FullLoader)

        r = Rule(rule)
        r.add_directives(rule)
        expected_rule = MatchRule(
            directive='transaction',
            parameter='narration',
            meta_key=None,
            regular_expressions={
                re.compile("AirBnB(.*)"),
                re.compile("Air BnB(.*)"),
                re.compile("BnB Payments(.*)")
            }
        )

        self.assertEqual(
            {'transaction-narration': expected_rule},
            r.match_requirements
        )


class TestMatchRule(unittest.TestCase):

    def test_eq(self):
        first = MatchRule(
            directive='transaction',
            parameter='narration',
            meta_key=None,
            regular_expressions={
                re.compile("Test")
            }
        )

        second = MatchRule(
            directive='transaction',
            parameter='narration',
            meta_key=None,
            regular_expressions={
                re.compile("Test")
            }
        )

        self.assertEqual(first, second)

        second.extend(first)

        self.assertEqual(first, second)

        third = MatchRule(
            directive='transaction',
            parameter='payee',
            meta_key=None,
            regular_expressions={
                re.compile("Test2")
            }
        )

        self.assertNotEqual(first, third)

        # Make sure we can't missmatch these Rules
        self.assertRaises(AssertionError, first.extend, third)

    def test_add_rule_meta_acct(self):
        rules = yaml.load("""
- match-narration: E*TRADE DES:ACH.*
  match-account: Assets:Banking:.*
  set-posting-account: Assets:Transfer
  set-posting-account-meta-account: Assets:Banking:ETrade:Cash
""", Loader=yaml.FullLoader)
        for rule in rules:
            Rule(rule)

    def test_match_1(self):
        entry = parser.parse_one("""
2020-04-08 ! "AMZN Mktp US*L08746BB3"
  match-key: "2020040824692160098100992944500"
  ofx-type: "DEBIT"
  * Liabilities:CreditCard:Chase:Amazon  -39.98 USD
  ! Expenses:FIXME                        39.98 USD
""")
        assert entry.flag == "!"
        ruler = Rule({
            'match-narration': "AMZN Mktp *.",
            'set-account': 'Expenses:Shopping'
        })
        result = ruler.check(entry)
        self.assertIsNotNone(result)
        new_entry = ruler.modify_entry(entry, result)
        self.assertEqual(new_entry.flag, '*')

    @parser.parse_doc()
    def test_match_2(self, entries, errors, option_map):
        """
2020-04-01 * "AMZN Mktp US*L08746BB3"
  match-narration: "AMZN Mktp.*"
  * Liabilities:CreditCard:Chase:Amazon  -39.98 USD
  * Expenses:Shopping:Amazon              39.98 USD

2020-04-08 ! "AMZN Mktp US*L08746BB3"
  match-key: "2020040824692160098100992944500"
  ofx-type: "DEBIT"
  * Liabilities:CreditCard:Chase:Amazon  -39.98 USD
  ! Expenses:FIXME                        39.98 USD
    """
        result, errors  = matcher.match_directives(entries, {})
        for entry in result:

            self.assertEqual(entry.flag, '*')

