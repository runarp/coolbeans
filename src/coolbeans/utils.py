import typing
import pathlib
import logging
import importlib
import pprint
import yaml


logger = logging.getLogger(__name__)


def get_project_root() -> pathlib.Path:
    """Returns project root folder."""
    return pathlib.Path(__file__).parent


def logging_config(config_file=None, level=logging.INFO):

    if not config_file:
        config_file = pathlib.Path(__file__).parent.joinpath("logging.yaml")

    config_file = pathlib.Path(config_file)
    assert config_file.exists(), f"Unable to find {config_file}"
#   if not config_file.exists():
#       return

    with config_file.open("r") as fil:
        config = yaml.full_load(fil)

        config.setdefault(
            'loggers',
            {'coolbeans': {}})['coolbeans']['level'] = level

        import logging.config
        logging.config.dictConfig(config)


def safe_plugin(func: typing.Callable) -> typing.Callable:
    # We might want to pull the logger out of the func module?
    DEBUG_CONTEXT = {}
    try:
        DEBUG_CONTEXT = getattr(importlib.import_module(func.__module__), 'DEBUG_CONTEXT', {})
        log = importlib.import_module(func.__module__).logger
    except AttributeError:
        log = logger

    def do_work(*args):
        log.info(f"Loading Plugin {func.__name__}")
        try:
            return func(*args)
        except Exception as e:
            log.exception(f"{func.__name__} {pprint.pformat(DEBUG_CONTEXT)}")
            raise

    return do_work

def get_setting(key, settings):
    """Returns the first item from the setting list if only one item"""
    if key in settings:
        value = settings[key]
        if isinstance(value, list):
            if len(value) == 1:
                return value[0]
            else:
                return value
        return value
