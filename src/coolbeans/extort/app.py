"""Utility to find/extract data from various strams and save into various JSON files."""
import argparse
import os
import json
import logging
import pathlib
import sys
import itertools

# coolbeans imports
from coolbeans.utils import logging_config
from coolbeans.tools.json import CoolJsonEncoder


logger = logging.getLogger(__name__)


EXTRA_ATTRIBUTES = ('source_account', 'slug')


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    logging_config("./logging.yaml", level=logging.DEBUG)

    parser.add_argument(
        "source",
        type=str,
        nargs="+",
        default="-"
    )
    parser.add_argument(
        "-t", "-o", "--target", "--output",
        type=argparse.FileType("w", encoding="utf-8"),
        default="-",
    )
    parser.add_argument(
        "--loader",
        type=str,
        dest="loader",
        required=True,
        help="Module name to load, use module:Classname if the Classname is not Extorter"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False
    )
    for name in EXTRA_ATTRIBUTES:
        parser.add_argument(
            f"--{name}",
            type=str,
            default="",
            help="Passed through into the record.",
        )

    args = parser.parse_args()

    # Default file_name
    # file_name = '.'.join([
    #     #  last_date.strftime('%Y-%m-%d') + first_str,
    #     #  slug,
    #     conf['account'].replace(':', '.'),
    #     'sheet',
    #     args.format
    # ])

    # out_file = output.joinpath(file_name)

    # TODO We need a clean way to get this meta-data into the stream.
    #  document = dict(
    #      records=records,
    #      document=conf['document'],
    #      tab=conf['tab'],
    #      slug=slug,
    #      account=conf['account'],
    #      saved=datetime.datetime.today(),
    #      from_date=first_date,
    #      until_date=last_date,
    #      version="1.0",
    #      currencies=conf['currencies']
    #  )

    sources = args.source
    target = args.target

    # Import the loader:
    import importlib
    if ':' in args.loader:
        e_module, e_class = args.loader.split(':')
    else:
        e_module, e_class = args.loader, "Extorter"

    extorter = importlib.import_module(e_module)
    klass = getattr(extorter, e_class)
    import os

    logging.debug(f"Looking at {sources}")
    files = []
    for file in sources:
        file_p = pathlib.Path(file)
        if file_p.is_file():
            if file_p.exists():
                files.append(file_p)
            else:
                logging.error(f"Unable to find file {file_p}")
        elif file_p.is_dir():
            files.extend(file_p.rglob("*"))

    logging.debug(f"Looking at {files}")

    for source in files:
        logging.debug(f"Looking at {source}")
        instance = klass(debug=args.debug)

        # We handle stdin and custom file modes (some require binary)
        if source == "-":
            if not instance.FILE_OPEN_MODE:
                print(f"Loader {e_module} doesn't support stdin.")
            source = sys.stdin
        else:
            if instance.FILE_OPEN_MODE:
                source = pathlib.Path(source).open(instance.FILE_OPEN_MODE)

        extra = {}
        for key in EXTRA_ATTRIBUTES:
            value = getattr(args, key)
            if value:
                extra[key] = value

        extra['source_file'] = source

        try:
            instance.set_header(extra)
            for record in instance.extort(source):
                json.dump(record, fp=target, indent=2, cls=CoolJsonEncoder)

                target.write('\n')

        except Exception as exc:
            logger.exception(f"While trying to process {source}")
            if args.debug:
                sys.exit(1)


if __name__ == "__main__":
    main()
