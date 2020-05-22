import typing
import logging
import importlib

logger = logging.getLogger(__name__)

def safe_plugin(func: typing.Callable) -> typing.Callable:
    # We might want to pull the logger out of the func module?
    try:
        log = importlib.import_module(func.__module__).logger
    except AttributeError:
        log = logger

    def do_work(*args):
        log.info(f"Loading Plugin {func.__name__}")
        try:
            return func(*args)
        except Exception as e:
            log.exception(f"{func.__name__}")
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
