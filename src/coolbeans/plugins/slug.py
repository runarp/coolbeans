# beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin


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
                slugs[slug.lower()] = entry.account
                slugs[slug.replace('-', '')] = entry.account

    return entries, []


account_slug_plugin = safe_plugin(account_slug)
