import fava.cli
import logging
import sys

from fava.application import app

from coolbeans.utils import logging_config

def main():
    logging_config(
        config_file="./logging.yaml",
        level=logging.DEBUG
    )
   #logging.basicConfig(
   #    stream=sys.stderr,
   #    level=logging.DEBUG
   #)
    fava.cli.main()

if __name__ == "__main__":
    main()

