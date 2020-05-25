"""Statement Filing CLI

CLI to let us use the Statement Filing Plugin

"""
# stdlib imports
import os
import sys
import argparse
import pathlib
import logging
import pprint
import typing

# beancount imports
from beancount.loader import load_file
from beancount.parser import printer

from coolbeans.tools.namematch import expand_file


logger = logging.getLogger(__name__)
BEAN_FILE_ENV = 'BEAN_FILE'


def filing_handler(
        source_directories: typing.List[pathlib.Path],
        destination: pathlib.Path,
        slugs: typing.Dict[str, str],
        dry_run=False
    ):

    for folder in source_directories:
        for file in folder.rglob("*"):
            match = expand_file(file)
            if match is None:
                continue

            account = slugs.get(match.slug, None)
            if not account:
                account = slugs.get(match.slug.replace('-', ''), None)
            if not account:
                logger.info(f"Unable to find matching account for slug {match.slug}. [{match.file}]")
                continue

            sub_directory = account.replace(':', '/')
            target_directory = destination.joinpath(sub_directory)

            # Just incase
            target_file = target_directory.joinpath(match.make_name)

            if not dry_run:
                target_directory.mkdir(parents=True, exist_ok=True)
                if not target_file.exists():
                    file.rename(target_file)
                else:
                    logger.warning(f"Skipping existing target {target_file}")
            else:
                if not (target_directory.exists() and target_directory.is_dir()):
                    logger.info(f"DRY: mkdir {target_directory}")
                if not target_file.exists():
                    logger.info(f"DRY: mv {file} -> {target_file}")



def configure_parser(parser):
    default_file = os.environ.get(BEAN_FILE_ENV, None)
    parser.add_argument(
        '-e', '--existing',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        type=pathlib.Path,
        dest='bean_file',
        help=f"Beancount file to read the Open slugs. {'Default is '+ default_file if default_file else ''}"
    )
    parser.add_argument(
        '-v', '--debug',
        action='store_true',
        default=False
    )
    parser.add_argument(
        dest='destination_folder',
        metavar='DESTINATION',
        type=pathlib.Path
    )
    parser.add_argument(
        dest='source_folders',
        metavar='SOURCE',
        nargs='+',
        type=pathlib.Path,
        help="Source folder(s) to scan for documents.",
        default=list()
    )
    return parser


def main():
    parser = argparse.ArgumentParser("Filing App")
    configure_parser(parser)

    args = parser.parse_args()

    if not args.bean_file.exists():
        print(f"Unable top find {args.bean_file}.")
        sys.exit(1)

    for folder in args.source_folders:
        assert isinstance(folder, pathlib.Path)
        if not folder.is_dir():
            print(f"Invalid source folder {folder}.")

    if not args.destination_folder.is_dir():
        print(f"Invalid destination folder {args.destination_folder}.")

    if args.debug:
        logging.basicConfig(
            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            level=logging.DEBUG,
            stream=sys.stderr
        )

    # Read the Beanfile
    logger.info(f"Loading {args.bean_file}.")
    entries, errors, context = load_file(
        args.bean_file,
        log_errors=logger.error,
        log_timings=logger.info
    )
    logger.info(f"Read {len(entries)} entries.")

    if errors:
        pprint.pprint(errors, stream=sys.stderr)
        # printer.print_errors(errors, sys.stderr)
        sys.exit(1)

    slugs = context['slugs']

    filing_handler(
        source_directories=args.source_folders,
        destination=args.destination_folder,
        slugs=slugs,
        dry_run=True
    )

if __name__ == "__main__":
    main()
