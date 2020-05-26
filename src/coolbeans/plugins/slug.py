import re
import logging
# beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin

logger = logging.getLogger(__name__)


__plugins__ = ['account_slug_plugin']

SLUG_OPEN_META_KEY = 'slug'  # name under meta
SLUG_CONTEXT_KEY = 'slugs'    # name in context


def account_slug(entries, context):
    """Given a set of entries, pull out any slugs and add them to the context"""
    slugs = context.setdefault(SLUG_CONTEXT_KEY, {})

    # Pull out any 'slug' meta data
    for entry in entries:
        if isinstance(entry, data.Open):
            slug = entry.meta.get(SLUG_OPEN_META_KEY, None)
            if slug:
                slug = slug.lower()
                multiple = re.split(r'[\s,]', slug)
                for s in multiple:
                    if not s:
                        continue
#                   if s.lower() in slugs:
#                       logger.warn(f"Duplicate slug {s.lower()} for {entry.account}")
#                   slugs[s.lower()] = entry.account
#                   if s.lower() in slugs:
#                       logger.warn(f"Duplicate slug {s.replace('-', '')} for {entry.account}")
                    slugs[s.replace('-', '')] = entry.account

    return entries, []


account_slug_plugin = safe_plugin(account_slug)
