"""
A single Match Rule.

Rules are helpful basic Units of match rules and transformations on a
single beancount entry.

Example (possible) interface:

To Load Rules:

    rules = Rule(r) for r in my_source_list_of_dicts

To check a Rule against an entry:

    for rule in rules:
        match =  rule.check(entry)

match is an instance of Match, which would contain any needed meta-data

To Transform an entry based on this Rule:

    new_entry = rule.apply(entry)

Open questions:

- Can a Rule modify more than one entry based on a single match?
- Can a Rule create an Entry?

"""
from __future__ import annotations
import yaml
import re
import pprint
import logging
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Set, Dict, Union, Iterator

from beancount.core import data
from beancount.parser import printer

logger = logging.getLogger(__name__)

KEY_RE = list(map(re.compile, [
    r"^(?P<command>set|match|test)$",
    r"^(?P<command>set|match|test)-(?P<parameter>\w+)$",
    r"^(?P<command>set|match|test)-((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>\w+)$",
    r"^(?P<command>set|match|test)-((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>meta)-(?P<meta_key>.*)$",
]))

SUB_KEY_RE = list(map(re.compile, [
    r"^(?P<parameter>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>meta)-(?P<meta_key>.*)$",
]))

VALID_COMMANDS = ('match', 'set', 'test')

TRANSACTION_PARAMETERS = (
    'narration',
    'tags',
    'payee',
    'narration',
    'links',
    'flag'
)

VALID_FIELDS = [
    'account',
    'payee',
    'date',
    'tags',
    'narration',
    'posting',
    'transaction',
    'links',
    'meta'
]


def match_any_re(regex_list, value):
    """Given a list of pre-compiled regular expressions,
    return the first match object.  Return None if there's no Match"""
    for regex in regex_list:
        match = regex.fullmatch(value)
        if match:
            return match.groupdict()


@dataclass
class DirectiveAttribute:
    """A Single Attribute on a Directive"""
    directive: str
    parameter: str
    meta_key: Optional[str]
    command: Optional[str] = field(default=None)
#   value: Optional[str, list] = field(default=None)

    def validate(self):
        assert self.command in VALID_COMMANDS, self
        if self.command != 'test':
            assert self.directive in ("transaction", "posting"), self


@dataclass
class SetRule(DirectiveAttribute):
    """A single transformation on a Directive

    """
    value: str = field(default="")


@dataclass
class MatchRule(DirectiveAttribute):
    """Capture a single list of Regular Expressions and the "path" to
    extract the value on an beancount Entry.

    """
    regular_expressions: Set[re.Pattern] = field(default_factory=set)

    def __eq__(self, other: MatchRule):
        """Compare, including Regex"""
        if other.__class__ is not self.__class__:
            return NotImplementedError
        return (self.directive, self.parameter, self.meta_key, self.regular_expressions) == (
            other.directive, other.parameter, other.meta_key, other.regular_expressions
        )

    def extend(self, other: MatchRule):
        assert self.directive == other.directive, self.directive
        assert self.parameter == other.parameter, self.parameter
        assert self.meta_key == other.meta_key, self.meta_key

        # Perhaps Use Set instead of a List
        for r in other.regular_expressions:
            if r not in self.regular_expressions:
                self.regular_expressions.add(r)

    @property
    def key(self):
        result = f"{self.directive}-{self.parameter}"
        if self.meta_key:
            result += f"-{self.meta_key}"
        return result

    def extract_value(self, entry):
        # Get the value on an entry
        obj = entry
        if self.directive == 'posting':
            # Find the first posting:
            for posting in entry.postings:

                # Use the first posting with a '*' flag
                if posting.flag == '*':
                    obj = posting
                    break
            else:
                return None

        # Now we don't care if it's a posting or object
        if self.parameter == 'meta':
            return obj.meta[self.meta_key]

        return str(getattr(obj, self.parameter))

    def match_entry(self, entry):
        value = self.extract_value(entry)

        if value is None:
            logger.info(f"Got None value for: {self}\n{printer.format_entry(entry)}")
            return

        history = MATCH_CHECK.setdefault(value, {'count': 0})
        history['count'] += 1

        for reg in self.regular_expressions:
            match = reg.match(value)
            if match:
                #  logger.info(f"Match:   {value:42} : {reg}")
                if hasattr(match, 'groupdict'):
                    history[reg] = match.groupdict()
                    return match.groupdict()
                else:
                    history[reg] = {}
                    return {}

            elif reg not in history:
                history[reg] = None

MATCH_CHECK = dict()

class Rule:
    """
    a Rule object captures a list of match criteria as well as a list
    of "actions".  These can be serialized in a dictionary and applied
    to entries.

    """
    # Dict (directive, key, meta-key) -> [values]
    match_requirements: dict = None
    set_rules: List[SetRule]

    actions: list = None
    assertions: list = None
    tests: list = None

    def __repr__(self):
        return f"""Rule(
            match_requirements={pprint.pformat(self.match_requirements)},
            set_rules={pprint.pformat(self.set_rules)},
        )"""

    def __init__(self, rule_dict: dict):
        # These are the Match rules
        self.match_requirements = {}
        self.set_rules = []

        # This is what to do if we match
        self.actions = []

        # Ideas for sanity checks
        self.assertions = []
        self.tests = []

        self.add_directives(rule_dict)

    def upset_match_rule(self, match_rule: MatchRule):
        existing = self.match_requirements.get(match_rule.key, None)
        if existing:
            existing.extend(match_rule)
            match_rule = existing
        else:
            self.match_requirements[match_rule.key] = match_rule
        return match_rule

    def default_key_match(self, key_match) -> dict:
        parameter = key_match.get('parameter', None)
        if parameter in ('narration', 'payee', 'tags', 'meta'):
            key_match.setdefault('directive', 'transaction')
        if parameter in ('account',):
            key_match.setdefault('directive', 'posting')

    def expand_rule_dict(self, rule_dict: dict) -> Iterator[DirectiveAttribute]:

        for key, value in rule_dict.items():
            if key == 'match-key': continue
            key_match = match_any_re(KEY_RE, key)

            if key_match is None:
                raise ValueError(f"Invalid Key format {key} in {rule_dict}")

            response = key_match
            self.default_key_match(key_match)

            command = response.pop('command', None)
            parameter = response.pop('parameter', None)
            directive = response.pop('directive', None)

            attr = DirectiveAttribute(
                command=command,
                directive=directive,
                parameter=parameter,
                meta_key=response.get('meta_key', None),
            )

            if command == 'test':
                attr.value = value
                yield attr

            # Is this code even related
            if isinstance(value, dict):
                for k, v in value.items():
                    key_match = match_any_re(SUB_KEY_RE, k)
                    if key_match is None:
                        raise ValueError(f"{type(value)} Invalid Key format {key} in {rule_dict}")
                    self.default_key_match(key_match)
                    r = key_match
                    attr.directive = r.get('directive', attr.directive)
                    attr.parameter = r.get('parameter', attr.parameter)
                    attr.meta_key = r.get('meta_key', attr.meta_key)
                    attr.value = v
                    yield attr
            else:
                attr.value = value
                yield attr

    def setdefault_params(self, attr: DirectiveAttribute) -> DirectiveAttribute:
        """Given a DirectiveAttribute, set the default paths for known attributes."""

        if attr.command == 'test':
            return attr
        if attr.directive in ('tx', 'trans'):
            attr.directive = 'transaction'
        if attr.parameter in TRANSACTION_PARAMETERS:
            assert attr.directive is None or attr.directive == 'transaction', (attr, TRANSACTION_PARAMETERS)
            attr.directive = 'transaction'
        elif attr.parameter in ('account',):
            assert attr.directive is None or attr.directive == 'posting'
            attr.directive = 'posting'
        elif attr.parameter in ('meta',):
            assert attr.meta_key, f"Meta requires an addition name, like 'match-meta-mykey {attr}"

        return attr

    def add_directives(self, rule_dict: dict):

        for da in self.expand_rule_dict(rule_dict):

            self.setdefault_params(da)
            da.validate()

            if da.command == 'match':

                # This str/list/set is a bit of a mess
                if isinstance(da.value, str):
                    values = {da.value}
                elif isinstance(da.value, list):
                    values = set(da.value)
                else:
                    values = da.value

                values = {re.compile(v, re.I) for v in values}

                m = MatchRule(
                    command='match',
                    parameter=da.parameter,
                    directive=da.directive,
                    meta_key=da.meta_key,
                    regular_expressions=values,
                )
                # Add it to our list of Match Rules
                self.upset_match_rule(m)

            if da.command == 'set':
                self.set_rules.append(
                    SetRule(
                        command='set',
                        parameter=da.parameter,
                        directive=da.directive,
                        meta_key=da.meta_key,
                        value=da.value,
                    )
                )

    def decode_value(self, value):
        if isinstance(value, str):
            try:
                value = yaml.load(value, Loader=yaml.FullLoader)
            except ValueError:
                pass
        return value

    def check(self, entry):
        """Check to see if an Entry matches this Rule.

        args:
            entry - an data.Transaction
        returns:
            None if there's no match
            dict if there's any match.  Note the dict might be empty.

        """
        result_dict = {}
        for key, match_requirement in self.match_requirements.items():
            match = match_requirement.match_entry(entry)
            if match is None:
                return None
            result_dict.update(match)
        return result_dict

    def modify_entry(
            self,
            entry: data.Transaction,
            match_values: dict,
            flag_to_done=True):
        """takes an Entry and a dict of values we parsed from the Entry
        """

        # Pre-process match_value?
        for sr in self.set_rules:

            if sr.directive == 'transaction':
                # Should Possible Eval the Value?
                if sr.meta_key:
                    # Meta Key is inserted
                    meta = dict(entry.meta)
                    meta[sr.meta_key] = sr.value
                    entry = entry._replace(meta=meta)
                else:
                    value = sr.value
                    if sr.parameter in ('links', 'tags'):
                        current:set = getattr(entry, sr.parameter, set()) or set()
                        current.add(value)
                        value = current

                    entry = entry._replace(**{sr.parameter: value})

            elif sr.directive == 'posting':
                postings = []
                for posting in entry.postings:
                    if posting.flag == '!':
                        if sr.meta_key:
                            meta = dict(posting.meta)
                            meta[sr.meta_key] = sr.value
                            posting = posting._replace(
                                meta=meta
                            )
                        else:
                            posting = posting._replace(**{
                                sr.parameter: sr.value
                            })
                        logger.debug(f"New POSTING: {posting}")
                    postings.append(posting)

                entry = entry._replace(postings=postings)

            for field, value in match_values.items():
                # We allow <payee> and <meta_tagname> in match-groups
                if field == "payee" and not entry.payee:
                    entry = entry._replace(payee=value.title())  # Propercase
                if field.startswith('meta_'):
                    meta_name = field[5:]
                    entry.meta[meta_name] = value

        if flag_to_done:
            # Set all ! -> *
            postings = []
            for posting in entry.postings:
                if posting.flag == '!':
                    posting = posting._replace(flag='*')
                postings.append(posting)
            entry = entry._replace(postings=postings, flag='*')

        return entry
