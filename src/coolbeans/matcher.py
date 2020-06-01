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

# stdlib imports
import pathlib
import sys
import re, yaml
import pprint
import logging
import argparse
import typing
from typing import Dict, List, Iterator, Optional
from dataclasses import dataclass, field

# Beancount Imports
from beancount.core import data
from beancount.core.data import Directive, Entries
from beancount.ingest import scripts_utils
from beancount.ingest.extract import print_extracted_entries
from beancount.parser.printer import format_entry, print_entries, print_errors

# Local imports
from coolbeans.utils import safe_plugin
from coolbeans.rule import Rule, MATCH_CHECK

logger = logging.getLogger(__name__)

__plugins__ = (
    'apply_coolbean_settings_plugin',
    'match_directives_plugin',
    'generate_new_rules_plugin'
)
__version__ = '1.0'

def apply_coolbean_settings(entries, options_map):
    settings = {}
    for entry in entries:
        if isinstance(entry, data.Custom):
            if entry.type == "coolbeans":
                param, value = entry.values
                settings.setdefault(param.value, []).append(value.value)

    options_map['coolbeans'] = settings

    return entries, []


apply_coolbean_settings_plugin = safe_plugin(apply_coolbean_settings)


def match_directives(entries, options_map, *args):
    """Modify any entries that Match existing Rules"""
    MATCH_CHECK.clear()
    rules = []

    # Make sure to have run the apply_coolbeans_settings_plugin
    settings = options_map['coolbeans']

    # Load a rules.yaml type file
    if 'rules-file' in settings:
        # We support multiple Rules Files
        for file_path in settings['rules-file']:
            file = pathlib.Path(file_path)
            if not file.exists():
                logger.warning(f"Unable to find Rules File {file}")
                continue

            # Read the YAML file
            with file.open("r") as stream:
                new_rules = yaml.full_load(stream)

            for rule in new_rules:
                rules.append(
                    Rule(rule)
                )
    output_file = settings.get('output-file', ['matched.bean'])[0]
    output_file = pathlib.Path(output_file)

    new_entries = []
    mod_entries = []
    no_match_entries = []
    possible_rules = {}

    # Now, see what we can actually Match:
    for entry in entries:

        # We're only interested in Pending Entries
        if getattr(entry, 'flag', None) != '!':
            # Pass through to new_entries
            new_entries.append(entry)
            continue

        # Check against all the Rules:
        modified = False
        for rule in rules:
            match_values = rule.check(entry)
            if entry.narration.lower().startswith('airbnb') and match_values:
                logger.info(f"{entry.narration.lower()}: {rule.match_requirements}: {match_values}")
            if match_values is None:
                continue
            entry = rule.modify_entry(entry, match_values)
            modified = True

        # Always pass it to our output stream
        new_entries.append(entry)

        if modified:
            mod_entries.append(entry)
        else:
            no_match_entries.append(entry)

    # We update the "suggestions" file
    with output_file.open("w") as outstream:
        print_entries(
            mod_entries,
            file=outstream
        )
        logger.info(f"cached: wrote {len(mod_entries)} entries to {output_file}")

    return new_entries, []

@dataclass
class PossibleRule:
    count: int = field(default=0)
    entry: Optional[data.Transaction] = field(default=None)
    narration: str = field(default="")
    match_account: str = field(default="")
    rule_account: str = field(default="")
    tags: str = field(default="")
    links: str = field(default="")
    payee: str = field(default="")
    amounts: list = field(default_factory=list)


def generate_new_rules(entries, options_map):
    """
    A Helper function to dig through a list of entries and generate a rules
    file. This is just a helper so you don't have to start with an empty file.
    """

    # Make sure to have run the apply_coolbeans_settings_plugin
    settings = options_map['coolbeans']
    rules_out_files: list = settings.get('gen-rules-file', [])
    if not rules_out_files:
        return
    rules_out = pathlib.Path(rules_out_files[0])

    # Generate a list of the good, bad and the ugly
    good_entries: List[data.Transaction] = []
    bad_entries: List[data.Transaction] = []

    good_by_name: Dict[str, data.Transaction] = {}
    bad_by_name: Dict[str, PossibleRule] = {}

    for entry in entries:
        if not isinstance(entry, data.Transaction):
            continue
        # The Good
        if entry.flag == "*" and entry.narration:
            good_entries.append(entry)
            n = entry.narration.lower()
            if n not in good_by_name:
                good_by_name[n] = entry

        # The Bad
        elif entry.flag == "!" and entry.narration:
            bad_entries.append(entry)
            n = entry.narration.lower()
            if n in bad_by_name:
                possible = bad_by_name[n]
                possible.count += 1
            else:
                possible = PossibleRule(
                    entry=entry,
                    narration=n,
                )
                bad_by_name[n] = possible

            for posting in entry.postings:
                amt = float(abs(posting.units.number))
                if amt not in possible.amounts:
                    possible.amounts += [amt]


    # Find Candidates for Rules (our bad entries)
    new_rules = []
    for n, possible in bad_by_name.items():
        # Need to list the matching accounts etc.
        account = ""
        for posting in possible.entry.postings:

            # Check for the amounts for our new-rules
            amt = float(abs(posting.units.number))
            if amt not in possible.amounts:
                possible.amounts += [amt]

            if posting.flag == "*":
                account = posting.account
        rule = {
            'match-narration': n,
            'match-account': account,
            'comment': {'count': possible.count, 'amounts':possible.amounts}
        }
        new_rules.append(rule)
        new_rules.sort(key=lambda item: (item['comment']['count'], item['match-narration']))

    #for entry in bad_entries:
    #    # Keep a count of matches for this entry:
    #    narration = entry.narration.lower().strip()

    #    if narration not in good_by_name:
    #        # Best Posting Account
    #        account = ""
    #        for posting in entry.postings:
    #            if posting.flag == "*":
    #                account = posting.account

    #        narrations[narration] = dict(
    #            count=0,
    #            value=entry.narration,
    #            account=account
    #        )

    ## Now generate rules for interesting transactions:
    #rules = []
    #for narration, details in narrations.items():
    #    # Perhaps make this a configurable
    #    if details['count'] <= 1:
    #        continue
    #    possible_entry = entry_by_name.get(details['value'], None)
    #    new_rule = {
    #        'match-narration': narration,
    #        'match-account': details['account'],
    #        'test': [details['value']]
    #    }
    #    if possible_entry:
    #        if possible_entry:
    #            target_account = None
    #            for posting in possible_entry.postings:
    #                if posting.account != details['account']:
    #                    target_account = posting.account
    #            if target_account:
    #                new_rule['set-posting-account'] = target_account
    #            if possible_entry.payee:
    #                new_rule['set-payee'] = possible_entry.payee
    #            if possible_entry.tags:
    #                new_rule['set-transaction-tags'] = repr(possible_entry.tags)

    with rules_out.open("w") as stream:
        yaml.dump(new_rules, stream)

    return entries, []

match_directives_plugin = safe_plugin(match_directives)
generate_new_rules_plugin = safe_plugin(generate_new_rules)

def generate_new_rules_file(entries, options_map):
    """Let's find unmatched Entries and generate a rules file."""
    pass


def rule_from_meta(entry: data.Transaction) -> Rule:
    """We use the Entry as a template to the Rule
    Copy the Narration, Payee, Tags, Expense Account etc.
    """
    rs = {}
    if entry.tags:
        rs['set-tags'] = entry.tags
    if entry.payee:
        rs['set-payee'] = entry.payee

    for posting in entry.postings:
        if posting.account.startswith('Expenses'):
            rs['set-posting-account'] = posting.account

    for k, v in entry.meta.items():
        if k.startswith('match-') or k.startswith('set-'):
            rs[k] = v
    r = Rule(rs)

    logger.info(f"Created a Fancy Rule: {rs} -> {repr(r)}")
    return r

@dataclass
class Match:
    entry: Directive
    rule: Rule
    data: Dict[str, str]


class Matcher:
    """Most of this code is dead."""
    rules: List[Rule] = None

    def __init__(self, rules=None):
        self.rules = []

        if rules:
            self.add_rules(rules)

    def add_rules(self, rules: List[dict]):
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

    def find_matches(self, existing_entries: Entries) -> Iterator[Match]:
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

        for action, entry_type, field, value in self.expand_set_fields(match.rule):
            logger.info(f"{action} {entry_type} {field} {value}")
            assert action == 'set'
            if entry_type == 'transaction':
                # Should Eval the
                entry = entry._replace(**{field: value})
            elif entry_type == 'posting':
                postings = []
                for posting in entry.postings:
                    if posting.flag == '!':
                        posting = posting._replace(**{field: value, 'flag': 'M'})

                    postings.append(posting)
                entry = entry._replace(postings=postings, flag='*')

            # Process groupdict:
            # pprint.pprint(match)
            for field, value in match['matches']['parameters'].items():
                if field == "payee" and not entry.payee:
                    entry = entry._replace(payee=value.title())  # Propercase
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
    """Possibly hook entry point bean CLI.  But we call directly for now."""
    parser.add_argument(
        '-e', '-f', '--existing', '--previous',
        metavar='BEANCOUNT_FILE',
        default=None,
        help=('Beancount file or existing entries for de-duplication '
              '(optional)')
    )

    #  parser.add_argument(
    #      '-r', '--rules',
    #      action='store',
    #      metavar='RULES_FILENAME',
    #      help=(
    #          'Rules specification file. '
    #          'This is a YAML file with Match Rules '
    #      )
    #  )
    return parser


def main():
    # We don't do much other the validate the file
    # The File needs to load the plugin coolbean.matcher
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG
    )

    from beancount import loader

    # Load the bean_file
    entries, errors, options_map = loader.load_file(args.existing)

    if errors:
        print_errors(errors)


if __name__ == "__main__":
    main()
