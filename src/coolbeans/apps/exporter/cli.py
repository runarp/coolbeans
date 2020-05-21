import logging
import argparse

# bean imports
from beancount import loader
from beancount.utils import misc_utils

def main():
    parser = argparse.ArgumentParser("Coolbeans Report Runner")

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

    extra_validations = False

    logging.basicConfig(
        level=logging.INFO if args.timings else logging.WARNING,
        format='%(levelname)-8s: %(message)s'
    )

    # Parse the input file.
    errors_file = None if args.no_errors else sys.stderr
    with misc_utils.log_time('beancount.loader (total)', logging.info):
        entries, errors, options_map = loader.load_file(
            args.filename,
            log_timings=logging.info,
            log_errors=errors_file,
            extra_validations=extra_validations
        )
