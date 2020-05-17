"""
A single Match Rule.

Rules are helpful basic Units of transformatin to a
beancount entry.
"""
import yaml
import re

MATCH_RE = list(map(re.compile, [
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
            return regex.groupdict()

class Rule:

    match_requirements: dict = None
    actions: list = None
    assertions: list = None
    tests: list = None

    def __init__(self):
        self.match_requirements = {}
        self.actions = []
        self.assertions = []
        self.tests = []

    def add_match_directive(self, key, value):

        key_parts = match_any_re(MATCH_RE, key)
        assert isinstance(key_parts, dict)

        if isinstance(value, str):
            # Rule should be in format match-[type]-[field]
            entity_type = key_parts.get('entity_type', None)
            field = key_parts.get('field', None)
            meta_name = key_parts.get('meta', None)

            if field in ('narration', 'tags', 'payee'):
                assert entity_type is None or entity_type == 'transaction'
                entity_type = 'transaction'
            elif field in ('account'):
                assert entity_type is None or entity_type == 'posting'
                entity_type = 'posting'
            elif field in ('meta'):
                assert meta_name, "Meta requires an addition name, like 'match-meta-mykey"

            self.match_requirements[(entity_type, field, meta_name)] = [value]
            return

    def add_action_directive(self, key, value):
        pass

    def add_tests_directive(self, key, value):
        pass

    def decode_value(self, value):
        if isinstance(value, str):
            try:
                value = yaml.load(value, Loader=yaml.FullLoader)
            except ValueError:
                pass
        return value

    def compile(self, rule:dict):
        """Given a dict, compile it into a list of
        match_requirements, actions, asserts and tests.
        """

        valid_commands = ['match', 'set', 'test']
        valid_fields = ['account', 'payee', 'date', 'tags', 'narration', 'posting', 'transaction']

        for key, value in rule.items():

            # We allow for embedded YAML, handle that case
            value = self.decode_value(value)
            key = key.lower().strip()

            if key.startswith('match'):
                self.add_match_directive(key, value)
            if key.startswith('set'):
                self.add_action_directive(key, value)
            if key == 'tests':
                self.add_tests_directive(key, value)


            command, *fields = key.split('-')
            assert command in valid_commands, f"{command} not found in {valid_commands}"

            for field in fields:
                assert field in valid_fields, (field, valid_fields)
