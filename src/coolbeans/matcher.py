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

Another Idea is to use custom rules:

2016-06-14 custom "matcher" "rule" '''yaml
  match-narration: (?P<payee>AirBnB).*
  match-account: Assets:.*
  set-posting-account: Income:AirBnB
'''

"""

import re, yaml
import pprint
import logging
import argparse
from typing import Dict, List, Iterator

from beancount.core import data
from beancount.ingest import scripts_utils
from beancount.ingest.extract import print_extracted_entries

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
            if result:
                print(f"{rex} MATCH!\n{memo}\n{result.groupdict()}")

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
    pprint.pprint(loaded)


class Matcher:
    rules: dict = None

    def __init__(self, rules=None):

        if rules:
            self.set_rules(rules)

    def load_yaml_file(self, file_name):
        with open(file_name, "r") as fil:
            self.rules = yaml.load(fil)

    def set_rules(self, rules, validate=True):
        if validate:
            self.validate_rules(rules)
        self.rules = rules

    def validate_rules(self, rules):
        """
        Quickly process and verify the rules
        :return:
        """
        for rule in rules:
            self.validate(rule)

    def validate(self, rule):
        valid_commands = ['match', 'set', 'test']
        valid_fields = ['account', 'payee', 'date', 'tags', 'narration', 'posting', 'transaction']

        for key, value in rule.items():
            command, *fields = key.split('-')
            assert command in valid_commands, f"{command} not found in {valid_commands}"

            for field in fields:
                assert field in valid_fields, (field, valid_fields)

        # Check all match Fields
        for field, values in self.expand_match_fields(rule).items():
            for expression in values:
                re.compile(expression)

    def expand_match_fields(self, rule) -> Dict[str, List[str]]:
        """
        Expanded, rules are in the format:
            'match' : {'field': ["regex1", "regex2"]}

        But this can be shortened to:
            {'match-field': 'regex1'}
        or
            {'match-field': ['regex1', 'regex2']}

        for example:
            {'match-narration': 'Amazon.*'}

        always returns the expanded rules:
            {'field': ['regex1', 'regex2'], ...}

        """
        # We use any 'match' dictionary as the starting point
        result = rule.get('match', {})

        for key, values in rule.items():
            if '-' not in key:
                continue
            command, *field = key.split('-')
            # Only handling Match Command
            if not command == "match":
                continue
            result[field[0]] = values

        # Wrap any strings a list:
        for key, values in result.items():
            if isinstance(values, str):
                result[key] = [values]

        return result

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
        """Check if the Entry Matches this Rule"""
        # Only support Transactions atm
        if not isinstance(entry, data.Transaction):
            return False

        matches = {}
        for param, expressions in self.expand_match_fields(rule).items():
            # param is the Transaction Attribute we match on
            # expressions is a list of regular expressions
            for pattern in expressions:

                entry_values = self.get_entry_values(entry, param)
                logger.info(f"Looking at {param}: {entry_values}")

                for value in entry_values:
                    match_obj = re.match(pattern, value)
                    if match_obj:
                        # Capture the details of this Match
                        matches[param] = {
                            'match-parameter': param,
                            'match-value': value,
                            'match-group': match_obj.groupdict()
                        }
                        break
        return matches

    def match(self, entry):
        """Accepts a BeanCount Entry and tries to find a Matching Rule."""
        for rule in self.rules:
            match_obj = self.match_rule(entry, rule)
            if match_obj:
                return {
                    'rule': rule,
                    'matches': match_obj,
                    'entry': entry
                }
        else:
            return

    def find_matches(self, existing_entries:List) -> List[Dict]:
        for entry in existing_entries:
            found = self.match(entry)
            if found:
                yield found

    def expand_set_fields(self, rule) -> Iterator:
        result = {}
        for key, value in rule.items():
            command, *params = key.split('-')
            if command != 'set':
                continue
            assert params[0] in ('transaction', 'posting'), params[0]

            entity = params[0]
            if len(params) == 2:
                # is like "set-posting-account"
                field = params[1]
                yield 'set', entity, field, value
            elif len(params) == 1:
                assert isinstance(value, dict), f"Expected a dict of param->value not {value}"
                for k, v in value.items():
                    yield 'set', entity, k, v

        return result

    def process_match(self, match:dict):
        """Accepts a match dict in format
            'rule': The Original Rule,
            'matches': the values that matched
            'entry': the entry to modify.
        """
        entry = match['entry']
        for action, entry_type, field, value in self.expand_set_fields(match['rule']):
            assert action == 'set'
            if entry_type == 'transaction':
                # Should Eval the
                entry = entry._replace(**{field:value})
            elif entry_type == 'posting':
                postings = []
                for posting in entry.postings:
                    if posting.flag == '!':
                        posting = posting._replace(**{field:value})
                    postings.append(posting)
                entry = entry._replace(postings=postings)
        match['entry'] = entry

    def process(self, existing_entries):
        results = []
        for match in self.find_matches(existing_entries):
            entry = self.process_match(match)
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

def run():
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()

    from beancount import loader
    from beancount.core import data
    # Load it
    entries, errors, options_map = loader.load_file(args.existing)


    # print(f"loaded {len(entries)} entries, with {len(errors)} errors.")
    rules = []

    for entry in entries:
        if isinstance(entry, data.Custom):
            print(f"{entry}")

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
    # pprint.pprint(rules)
    m = Matcher(rules)
    updated_entries = []
    result = m.process(entries)

    for obj in result:
        updated_entries.append(obj['entry'])

    import sys
    print_extracted_entries(updated_entries, sys.stdout)

if __name__ == "__main__":
    run()

