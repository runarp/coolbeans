"""cool-check is an enhanced logging version of bean-check with pdb."""
from coolbeans.utils import logging_config

import argparse
import logging
import sys
import os
from pathlib import Path
import pdb


from beancount import loader
from beancount.ops import validation
from beancount.utils import misc_utils

from coolbeans.apps import BEAN_FILE_ENV


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    default_file = os.environ.get(BEAN_FILE_ENV, None)

    parser.add_argument(
        '-e', '--bean',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        required=False,
        type=str,
        dest='bean_file',
        help=f"Beancount file to read and verify. {'Default is '+ default_file if default_file else ''}"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print timings.'
    )
    parser.add_argument(
        '--pdb',
        action='store_true',
        help='Drop into a debugger on error'
    )
    parser.add_argument(
        '--logging-conf',
        type=str,
        default='./logging.yaml',
        help='logging.yaml file to use.  Default is ./logging.yaml'
    )
    args = parser.parse_args()

    logging_conf: Path = Path(args.logging_conf)

    logging_config(
        config_file=logging_conf,
        level=logging.DEBUG if args.verbose else logging.INFO
    )

    with misc_utils.log_time('beancount.loader (total)', logging.info):
        # Load up the file, print errors, checking and validation are invoked
        # automatically.
        try:
            entries, errors, _ = loader.load_file(
                args.bean_file,
                log_timings=logging.info,
                log_errors=sys.stderr,
                # Force slow and hardcore validations, just for check.
                extra_validations=validation.HARDCORE_VALIDATIONS)
        except Exception as exc:
            if args.pdb:
                pdb.post_mortem(exc.__traceback__)
            else:
                raise

if __name__ == "__main__":
    main()
