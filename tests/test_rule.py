import re
import yaml
import unittest
import pprint

from coolbeans.rule import MATCH_KEY_RE, Rule, MatchRule


class TestMatches(unittest.TestCase):

    def match_any(self, regex_list, value, expected_groupdict):

        match = None
        regex = None
        for regex in regex_list:
            match = regex.fullmatch(value)
            print(f"{value} ?~ {regex} ({match})")
            if match:
                break

        if not match:
            self.assertIs(expected_groupdict, None, f"{value} !! {regex}")
        else:
            self.assertEqual(expected_groupdict, match.groupdict(), f"{value} !! {regex}")

    def test_match_re_1(self):
        self.match_any(MATCH_KEY_RE, "miss", None)
        self.match_any(MATCH_KEY_RE, "match", {})

    def test_match_re_3(self):
        self.match_any(MATCH_KEY_RE, "match-narration", {'field': 'narration'})

    def test_match_re_2(self):
        self.match_any(
            MATCH_KEY_RE,
            "match-transaction-narration",
            {'field': 'narration', 'directive': 'transaction'}
        )

    def test_match_re_meta(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1", {
            'field': 'meta',
            'directive': 'tx',
            'meta': 'custom1'
        })

    def test_match_re_meta_with_dash(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1-field", {
            'field': 'meta',
            'directive': 'tx',
            'meta': 'custom1-field'
        })

    def test_match_re_meta_with_dash_no_entity(self):
        self.match_any(MATCH_KEY_RE, "match-meta-custom1-field", {
            'field': 'meta',
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
        r.compile(rule)
        expected_rule = MatchRule(
            entity_type='transaction',
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
        r.compile(rule)
        expected_rule = MatchRule(
            entity_type='transaction',
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
            entity_type='transaction',
            parameter='narration',
            meta_key=None,
            regular_expressions={
                re.compile("Test")
            }
        )

        second = MatchRule(
            entity_type='transaction',
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
            entity_type='transaction',
            parameter='payee',
            meta_key=None,
            regular_expressions={
                re.compile("Test2")
            }
        )

        self.assertNotEqual(first, third)

        # Make sure we can't missmatch these Rules
        self.assertRaises(AssertionError, first.extend, third)
