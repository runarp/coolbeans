import re
import unittest

from coolbeans.rule import MATCH_KEY_RE


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
        self.match_any(MATCH_KEY_RE, "match-transaction-narration", {'field': 'narration', 'entity_type': 'transaction'})

    def test_match_re_meta(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1", {
            'field':'meta',
            'entity_type': 'tx',
            'meta': 'custom1'
        })

    def test_match_re_meta_with_dash(self):
        self.match_any(MATCH_KEY_RE, "match-tx-meta-custom1-field", {
            'field':'meta',
            'entity_type': 'tx',
            'meta': 'custom1-field'
        })

    def test_match_re_meta_with_dash_no_entity(self):
        self.match_any(MATCH_KEY_RE, "match-meta-custom1-field", {
            'field':'meta',
            'entity_type': None,
            'meta': 'custom1-field'
        })

    def test_require_full(self):
        self.match_any(MATCH_KEY_RE, "XXXmatch-meta-custom1-field", None)

    def test_require_full2(self):
        self.match_any(MATCH_KEY_RE, "match__", None)
