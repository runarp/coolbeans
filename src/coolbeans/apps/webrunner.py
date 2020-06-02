
import logging

import fava.cli
from coolbeans.utils import logging_config


def main():
    logging_config(
        config_file="./logging.yaml",
        level=logging.DEBUG
    )
    fava.cli.main()

if __name__ == "__main__":
    main()
