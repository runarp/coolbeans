"""
Manage a Match file of Regulare Expressions that
attempt to define the account/tag/payee and Meta
Data for any incoming transaction

Idea is to use a YAML file with simple Rules:

match.yaml

'''yaml
    - rule-type: memo
      match-re:
      - r"(?P<payee>Amazon.com|amzn mktp us)\*(?P<order_id>.*)",
      - r"(?P<payee>Amazon.com)\*(?P<order_id>.*)",
      - r"(?P<payee>amzn mktp us)\*(?P<order_id>.*)",
      actions:
'''

Rules can be added by modifying the rules.yaml file directly, or by inlining
them/extracting them from the beancount source files.  This is through.

# Option 1
2016-06-14 custom "matcher" "rule" '''
  match-narration: (?P<payee>AirBnB).*
  match-account: Assets:.*
  set-posting-account: Income:AirBnB

## Option 2

In this case the Payee and Income Account will automatically be set.

2019-09-11 * "AirBnB" "Deposit - AIRBNB PAYMENTS"
  match-key: "201909110615000000000"
  match-narration: "(?P<payee>AirBnB).*"
  * Assets:Banking:BofA:Checking   1039.80 USD
  * Income:AirBnB                 -1039.80 USD

Internally we process things in the following order:

* Read any provide YAML File and build a list of Rules
* Read the 'existing' beans file if provided
* Find Any Custom Rule Directives, add those.
* Find Any Rules hidden in Meta Data.  Add Those.

With this "master" list of Rules. We "compile" them.  Rules
are often in short-hand.  The compiled rules are instances of Rule.

"""

import sys
import re, yaml
import pprint
import logging
import argparse
from dataclasses import dataclass
from typing import Dict, List, Iterator, Union, Optional

from beancount.core import data
from beancount.core.data import Directive, Entries
from beancount.ingest import scripts_utils
from beancount.ingest.extract import print_extracted_entries
from beancount.parser.printer import format_entry

from coolbeans.rule import Rule


logger = logging.getLogger(__name__)


def mainX():
    some_data = [
        "Amazon.com*MO7IO3OL2",
        "AMZN Mktp US*MA23B5WO1",
        "Amazon.com*MA4TS16T0",
        "AMZN Mktp US*MA0HF9660",
        "AMZN Mktp US*MA4O62W21",
        "PAL AIR     0797335735638",
        "STARBUCKS BORACAY AIRP AKLAN",
        "GRAB *40438931-9-103",
    ]

    rex_list = [
        r"(?P<payee>Amazon.com|amzn mktp us)\*(?P<order_id>.*)",
        r"(?P<payee>Amazon.com)\*(?P<order_id>.*)",
        r"(?P<payee>amzn mktp us)\*(?P<order_id>.*)",
        r"(?P<payee>starbucks)\s*(?P<location_id>.*)",
        r"(?P<payee>pal air)\s*(?P<location_id>.*)",
    ]

    rex_list = yaml.load(yaml.dump(rex_list), Loader=yaml.FullLoader)

    for memo in some_data:
        for rex in rex_list:
            result: re.Match = re.match(rex, memo, re.IGNORECASE)
#           if result:
#               print(f"{rex} MATCH!\n{memo}\n{result.groupdict()}")

    sample_struct = [
        {
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
            'set-transaction': {
                "payee": "Amazon",
                "tags": "kids",
                "meta": {"order-id": "{order_id}"}
            },
            'set-posting': {
                "account": "Expenses:Shopping",
            },
            'tests': {
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
        },
        {
            'match-narration': r"(?P<payee>starbucks)\s*(?P<meta_location_id>.*)",
            'set-posting-account': 'Expenses:Dining:Coffee',
        }
    ]
    dumped = yaml.dump(sample_struct)
    loaded = yaml.load(dumped, Loader=yaml.FullLoader)
    # pprint.pprint(loaded)

@dataclass
class Match:
    entry: Directive
    rule: Rule
    data: Dict[str, str]


class Matcher:
    rules: List[Rule] = None

    def __init__(self, rules=None):
        self.rules = []

        if rules:
            self.add_rules(rules)

    def load_yaml_file(self, file_name):
        with open(file_name, "r") as fil:
            rules = yaml.load(fil, Loader=yaml.FullLoader)
            self.validate_rules(rules)
            self.rules.extend(rules)

    def add_rules(self, rules: List[Rule]):
        for rule_dict in rules:
            self.rules.append(Rule(rule_dict))

    def get_entry_values(self, entry, attribute) -> List[str]:
        """Give an beancount entry, fish for this attribute.  Return a list
        of the values, even if there's just one.

        """
        if attribute in ('narration', 'payee'):
            value = getattr(entry, attribute)
            return [value]
        if attribute in ('tags', 'links'):
            value = getattr(entry, attribute)
            return list(value)
        if attribute == 'account':
            return [p.account for p in entry.postings]
        raise ValueError(f"Unknown attribute {attribute}")

    def match_rule(self, entry: data.Transaction, rule):
        """Match a Single Rule to a Transaction.

        Returns either None or an object describing the Match.
        """
        logger.debug(f"""Matching: {format_entry(entry)}""")

        # Only support Transactions atm
        if not isinstance(entry, data.Transaction):
            return False


        matches = {'parameters': {}}
        for param, expressions in self.expand_match_fields(rule).items():

            # print(f"{param}, {expressions}")

            # param is the Transaction Attribute we match on
            # expressions is a list of regular expressions
            found = False
            for pattern in expressions:

                entry_values = self.get_entry_values(entry, param)

                for value in entry_values:
                    match_obj = re.match(pattern, value, flags=re.IGNORECASE)
                    if value.lower().find("amazon") >= 0:
                        logger.info(f"Looking at {param}: {value} {pattern} {match_obj}")

                    if match_obj:
                        # Capture the details of this Match, strip whitespace just for good measure
                        matches['parameters'].update(dict((k, v.strip()) for k, v in match_obj.groupdict().items()))
                        matches[param] = {
                            'match-parameter': param,
                            'match-value': value,
                            'match-group': match_obj.groupdict()
                        }
                        found = True
                        logger.debug(f"Found! {matches}")

                        if False:
                            pprint.pprint(rule)
                            pprint.pprint(matches)
                            sys.exit(1)
                        break
                if found:
                    break

            # This is completely Broken.
            if not found:
                logger.debug(f"Return NO MATCHES")
                return {}
        logger.debug(f"Returning {matches}")
        return matches

    def match(self, entry: Directive) -> Optional[Match]:
        """Accepts a BeanCount Entry and tries to find a Matching Rule."""
        for rule in self.rules:
            match = rule.check(entry)
            if match is not None:
                return Match(
                    entry=entry,
                    rule=rule,
                    data=match
                )
        else:
            return

    def find_matches(self, existing_entries:Entries) -> Iterator[Match]:
        for entry in existing_entries:
            # Check Entry Type
            if not isinstance(entry, data.Transaction):
                continue

            if entry.flag != '!':
                continue

            found = self.match(entry)
            if found:
                yield found

    def expand_set_fields(self, rule) -> Iterator:
        result = {}
        for key, value in rule.items():
            command, *params = key.split('-')
            if command != 'set':
                continue

            entity = params[0]
            if entity in ('payee', 'narration'):
                yield 'set', 'transaction', entity, value
            elif len(params) == 2:
                assert params[0] in ('transaction', 'posting'), params[0]
                # is like "set-posting-account"
                field = params[1]
                yield 'set', entity, field, value
            elif len(params) == 1:
                assert isinstance(value, dict), f"Expected a dict of param->value not {value}"
                for k, v in value.items():
                    yield 'set', entity, k, v

        return result

    def process_match(self, match: Match):
        """Accepts a Match object

            'rule': The Original Rule,
            'matches': the values that matched
            'entry': the entry to modify.
        """

        entry = match.entry
        logger.info(pprint.pformat(match))

        for action, entry_type, field, value in self.expand_set_fields(match.rule):
            logger.info(f"{action} {entry_type} {field} {value}")
            assert action == 'set'
            if entry_type == 'transaction':
                # Should Eval the
                entry = entry._replace(**{field:value})
            elif entry_type == 'posting':
                postings = []
                for posting in entry.postings:
                    if posting.flag == '!':
                        posting = posting._replace(**{field:value, 'flag':'M'})

                    postings.append(posting)
                entry = entry._replace(postings=postings, flag='*')

            # Process groupdict:
            # pprint.pprint(match)
            for field, value in match['matches']['parameters'].items():
                if field == "payee" and not entry.payee:
                    entry = entry._replace(payee=value.title()) # Propercase
                if field.startswith('meta_'):
                    meta_name = field[5:]
                    entry.meta[meta_name] = value

        match['entry'] = entry

    def process(self, existing_entries):
        results = []
        for match in self.find_matches(existing_entries):
            entry = self.process_match(match)

            # pprint.pprint(match)
            results.append(match)
        return results

def add_arguments(parser):
    """Called by bean framework"""
    parser.add_argument(
        '-e', '-f', '--existing', '--previous',
        metavar='BEANCOUNT_FILE',
        default=None,
        help=('Beancount file or existing entries for de-duplication '
              '(optional)')
        )
    parser.add_argument(
        '-r', '--rules',
        action='store',
        metavar='RULES_FILENAME',
        help=(
            'Rules specification file. '
            'This is a YAML file with Match Rules '
        )
    )
    return parser

def main():
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()

    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    from beancount import loader
    from beancount.core import data

    # Load it
    entries, errors, options_map = loader.load_file(args.existing)

    rules:List[Rule] = []

    for entry in entries:
#       if isinstance(entry, data.Custom):

        if 'match-re' in entry.meta:
            value = entry.meta['match-re']
            regex = re.compile(str(value))
            match = regex.match(str(entry.narration))
            # match = re.match(regex, str(entry.narration))
            if not match:
                logger.warning(f"Ignoring failing {regex} on {entry.narration}")
                continue
            rules.append(
                {'match-narration': value,
                 'set-posting-account': entry.postings[-1].account,
                 'set-transaction-payee': entry.payee
                }
            )
    m = Matcher(rules)
    updated_entries = []

    if args.rules:
        m.load_yaml_file(args.rules)

    result = m.process(entries)

    for obj in result:
        updated_entries.append(obj['entry'])

    print_extracted_entries(updated_entries, sys.stdout)

if __name__ == "__main__":
    main()

