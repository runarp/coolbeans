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
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Set, Dict, Union

from beancount.core import data


# We use MATCH_KEY_RE to capture the valid keys in our Rules Dict
MATCH_KEY_RE = list(map(re.compile, [
    r"match",
    r"^match-(?P<field>\w+)$",
    r"^match-((?P<directive>tx|transaction|posting|pst)-)?(?P<field>\w+)$",
    r"^match-((?P<directive>tx|transaction|posting|pst)-)?(?P<field>meta)-(?P<meta>.*)$",
]))

# We use MATCH_KEY_RE to capture the valid keys in our Rules Dict
MATCH_SUB_KEY_RE = list(map(re.compile, [
    r"^(?P<field>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<field>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<field>meta)-(?P<meta>.*)$",
]))

KEY_RE = list(map(re.compile, [
    r"^(?P<command>set|match|test)$",
    r"^(?P<command>set|match|test)-(?P<field>\w+)$",
    r"^(?P<command>set|match|test)-((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>\w+)$",
    r"^(?P<command>set|match|test)-((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>meta)-(?P<meta_key>.*)$",
]))

SUB_KEY_RE = list(map(re.compile, [
    r"^(?P<field>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>\w+)$",
    r"^((?P<directive>tx|transaction|posting|pst)-)?(?P<parameter>meta)-(?P<meta_key>.*)$",
]))

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
    command: Optional[str]
    directive: str
    parameter: str
    meta_key: Optional[str]

@dataclass
class SetRule(DirectiveAttribute):
    """A single transformation on a Directive

    """
    value: str

@dataclass
class MatchRule(DirectiveAttribute):
    """Capture a single list of Regular Expressions and the "path" to
    extract the value on an beancount Entry.

    """
    regular_expressions: Set[re.Pattern]

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
                # Use the first posting with a '!' flag
                if posting.flag == '!':
                    obj = posting
                    break
            else:
                return None

        # Now we don't care if it's a posting or object
        if self.parameter == 'meta':
            return obj.meta[self.meta_key]

        return getattr(obj, self.parameter)

    def match_entry(self, entry):
        value = self.extract_value(entry)
        for reg in self.regular_expressions:
            match = reg.match(value)
            if match:
                if hasattr(match, 'groupdict'):
                    return match.groupdict()
                else:
                    return {}


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

    def __init__(self, rule_dict):
        # These are the Match rules
        self.match_requirements = {}
        self.set_rules = []

        # This is what to do if we match
        self.actions = []

        # Ideas for sanity checks
        self.assertions = []
        self.tests = []

        self.compile(rule_dict)

    def upset_match_rule(self, match_rule: MatchRule):
        existing = self.match_requirements.get(match_rule.key, None)
        if existing:
            existing.extend(match_rule)
            match_rule = existing
        else:
            self.match_requirements[match_rule.key] = match_rule
        return match_rule

    def add_match_directive(self, key, value):
        """
        Match directives can be explicit or nested dictionaries.

        - match:
            narration: AirBnB(.*)
        # and
        - match-narration: AirBnB(.*)

        are the same thing.  So we do some work to decode this.

        """
        key_parts = match_any_re(MATCH_KEY_RE, key)
        assert isinstance(key_parts, dict), f"Unable to parse {key} as a match directive."

        if isinstance(value, dict):
            assert key == 'match', "Only expect a dict under a 'match' directive"

            for field_name, nested_value in value.items():

                key_parts = match_any_re(MATCH_SUB_KEY_RE, field_name)

                # Duplicated from below, need to clean up
                entity_type = key_parts.get('directive', None)
                field = key_parts.get('field', None)
                meta_name = key_parts.get('meta', None)
                print(f"directive={entity_type}, field={field}, meta_name={meta_name}")
                if field in ('narration', 'tags', 'payee'):
                    assert entity_type is None or entity_type == 'transaction'
                    entity_type = 'transaction'
                elif field in ('account',):
                    assert entity_type is None or entity_type == 'posting'
                    entity_type = 'posting'
                elif field in ('meta',):
                    assert meta_name, "Meta requires an addition name, like 'match-meta-mykey"

                if isinstance(nested_value, str):
                    values = {nested_value}
                else:
                    values = nested_value
                values = {re.compile(v) for v in values}

                match_rule = MatchRule(
                    entity_type=entity_type,
                    parameter=field,
                    meta_key=meta_name,
                    regular_expressions=values
                )
                print(f"**** Upsert {match_rule}")
                self.upset_match_rule(match_rule)

        if isinstance(value, (str, list)):
            # Rule should be in format match-[type]-[field]
            entity_type = key_parts.get('directive', None)
            field = key_parts.get('field', None)
            meta_name = key_parts.get('meta', None)

            if field in ('narration', 'tags', 'payee'):
                assert entity_type is None or entity_type == 'transaction'
                entity_type = 'transaction'
            elif field in ('account',):
                assert entity_type is None or entity_type == 'posting'
                entity_type = 'posting'
            elif field in ('meta',):
                assert meta_name, "Meta requires an addition name, like 'match-meta-mykey"

            if isinstance(value, str):
                values = {value}
            else:
                values = value
            values = {re.compile(v) for v in values}

            match_rule = MatchRule(
                entity_type=entity_type,
                parameter=field,
                meta_key=meta_name,
                regular_expressions=values
            )
            self.upset_match_rule(match_rule)

    def expand_rule_dict(self, rule_dict: Dict[str, Union[str, List[str], dict]]) -> DirectiveAttribute:
        for key, value in rule_dict.items():
            key_match = re.match(KEY_RE, key)
            if not key_match:
                raise ValueError(f"Invalid Key format {key} in {rule_dict}")

            response = key_match.groupdict()
            command = response.pop('command', None)

            attr = DirectiveAttribute(**response)

            if isinstance(value, dict):
                for k, v in value.items():
                    key_match = re.match(SUB_KEY_RE, k)
                    if not key_match:
                        raise ValueError(f"Invalid Key format {key} in {rule_dict}")
                    r = key_match.groupdict()
                    attr = 1
                    r.update(response)
                    r['value'] = v
                    yield r
            else:
                response['value'] = value
                yield value

    def setdefault_params(self, attr: DirectiveAttribute) -> DirectiveAttribute:
        # assert params.command in ('set', 'match', 'test')

       #entity_type = params.get('directive', None)
       #field = params.get('field', None)
       #meta_name = params.get('meta', None)
        if attr.directive in ('tx', 'trans'):
            attr.directive = 'transaction'

        if attr.parameter in ('narration', 'tags', 'payee'):
            assert attr.directive is None or attr.directive == 'transaction'
            attr.directive = 'transaction'
        elif attr.parameter in ('account',):
            assert attr.directive is None attr.directive == 'posting'
            attr.directive = 'posting'
        elif attr.parameter in ('meta',):
            assert attr.meta_key, "Meta requires an addition name, like 'match-meta-mykey"

        return attr

    def add_directives(self, rule_dict):
        for params in self.expand_rule_dict(rule_dict):
            self.setdefault_params(params)

            if params['command'] == 'set':
                self.set_rules.append(
                    SetRule(
                        parameter=params['field'],
                        entity_type=params['directive'],
                        meta_key=params['meta'],
                        value=params['value']
                    )
                )

    def add_tests_directive(self, key, value):
        self.tests = value

    def decode_value(self, value):
        if isinstance(value, str):
            try:
                value = yaml.load(value, Loader=yaml.FullLoader)
            except ValueError:
                pass
        return value

    def compile(self, rule: dict):
        """Given a dict, compile it into a list of
        match_requirements, actions, asserts and tests.
        """
        # pprint.pprint(rule)

        valid_commands = ['match', 'set', 'test']
        valid_fields = [
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
        for key, value in rule.items():

            # Is this needed yet?
            command, *fields = key.split('-')
            assert command in valid_commands, f"{command} not found in {valid_commands}"

            # We allow for embedded YAML, handle that case
            value = self.decode_value(value)
            key = key.lower().strip()

            # Each directive type has its own processor
            if key.startswith('match'):
                print(f"Adding {key} {value}")
                self.add_match_directive(key, value)
            if key.startswith('set'):
                self.add_action_directive(key, value)
            if key == 'tests':
                self.add_tests_directive(key, value)

            for field in fields:
                assert field in valid_fields, (field, valid_fields)

    def check(self, entry):
        result_dict = {}
        for match_requirement in self.match_requirements:
            match = match_requirement.match_entry(entry)
            if match is None:
                return None
            result_dict.update(match)
        return result_dict


