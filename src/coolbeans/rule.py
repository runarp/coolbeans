"""
A single Match Rule.

Rules are helpful basic Units of match rules and transformations on a
single beancount entry.

Example (possible) interface:

To Load Rules:

    rules = Rule(r) for r in my_source_list_of_dicts

To check a Rule against an entry:

    for rule in rules:
        match =  rule.check_match(entry)

match is an instance of Match, which would contain any needed meta-data

To Transform an entry based on this Rule:

    new_entry = rule.apply(entry)

Open questions:

- Can a Rule modify more than one entry based on a single match?
- Can a Rule create an Entry?

"""
import yaml
import re
import pprint
from dataclasses import dataclass
from typing import List, Optional


# We use MATCH_KEY_RE to capture the valid keys in our Rules Dict
MATCH_KEY_RE = list(map(re.compile, [
    r"match",
    r"^match-(?P<field>\w+)$",
    r"^match-((?P<entity_type>tx|transaction|posting|pst)-)?(?P<field>\w+)$",
    r"^match-((?P<entity_type>tx|transaction|posting|pst)-)?(?P<field>meta)-(?P<meta>.*)$",
]))


def match_any_re(regex_list, value):
    """Given a list of pre-compiled regular expressions,
    return the first match object.  Return None if there's no Match"""
    for regex in regex_list:
        match = regex.fullmatch(value)
        if match:
            return match.groupdict()


@dataclass
class MatchRule:
    """Capture a single list of Regular Expressions and the "path" to
    extract the value on an beancount Entry.

    """
    entity_type: str
    parameter: str
    meta_key: Optional[str]
    regular_expressions: List[re.Pattern]

    @property
    def key(self):
        result = f"{self.entity_type}-{self.parameter}"
        if self.meta_key:
            result += f"-{self.meta_key}"
        return result

    def extract_value(self, entry):
        # Get the value on an entry
        obj = entry
        if self.entity_type == 'posting':
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
    # Dict (entity_type, key, meta-key) -> [values]
    match_requirements: dict = None

    actions: list = None
    assertions: list = None
    tests: list = None

    def __init__(self, rule_dict):
        # These are the Match rules
        self.match_requirements = {}

        # This is what to do if we match
        self.actions = []

        # Ideas for sanity checks
        self.assertions = []
        self.tests = []

        self.compile(rule_dict)

    def parse_expanded_match_key(self, key, value):
        """
        expects a key in the format:
        match-[entity]-[field][-[optional meta key]], value
        """

    def add_match_field_directive(self, field_name, value):
        assert field_name in ('account', 'narration', 'meta', 'payee')
        match_rule = MatchRule(
            entity_type='transaction',
            parameter=field_name,
            meta_key=None,
            regular_expressions=[re.compile(value)]
        )
        self.match_requirements[match_rule.key] = match_rule

    def match_dict_walker(self, key, value):
        """Given a key, value return all of the MatchRules
        """

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
            for field_name, v in value.items():
                # Process all of these match directives
                self.add_match_field_directive(field_name, v)

        if isinstance(value, str):
            # Rule should be in format match-[type]-[field]
            entity_type = key_parts.get('entity_type', None)
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

            match_rule = MatchRule(
                entity_type=entity_type,
                parameter=field,
                meta_key=meta_name,
                regular_expressions=[re.compile(value)]
            )

            # Need better handling of this case
            assert match_rule.key not in self.match_requirements, (
                f"Duplicate Match rule for {match_rule.key}"
            )

            self.match_requirements[match_rule.key] = match_rule

    def add_action_directive(self, key, value):
        self.actions = value

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
        pprint.pprint(rule)

        valid_commands = ['match', 'set', 'test']
        valid_fields = ['account', 'payee', 'date', 'tags', 'narration', 'posting', 'transaction']

        for key, value in rule.items():

            # Is this needed yet?
            command, *fields = key.split('-')
            assert command in valid_commands, f"{command} not found in {valid_commands}"

            # We allow for embedded YAML, handle that case
            value = self.decode_value(value)
            key = key.lower().strip()

            # Each directive type has its own processor
            if key.startswith('match'):
                self.add_match_directive(key, value)
            if key.startswith('set'):
                self.add_action_directive(key, value)
            if key == 'tests':
                self.add_tests_directive(key, value)

            for field in fields:
                assert field in valid_fields, (field, valid_fields)
