# -*- coding: utf-8; -*-
#
# Licensed to Crate (https://crate.io) under one or more contributor
# license agreements.  See the NOTICE file distributed with this work for
# additional information regarding copyright ownership.  Crate licenses
# this file to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
# However, if you have executed another commercial license agreement
# with Crate these terms will supersede the license and you may use the
# software solely pursuant to the terms of the relevant commercial agreement.

__docformat__ = "reStructuredText"

import os
import re
import json

from datetime import datetime
from markdown2 import markdown

from django.template import Context
from django.template.loader import get_template
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe

from web.utils import toDict, parseDate, parsePost

COLLECTIONS = dict()
COLLECTIONS_JSON = dict()
# legacy stuff
NEWS_JSON = []
DEVELOPER_NEWS_JSON = []


class Collection(object):

    CONTEXT_RAW_KEY = 'raw_body'
    CONTEXT_OUTPUT_KEY = 'body'

    def __init__(self, title, path, template, pages=[], config={}):
        self.title = title
        self.path = path
        self.template = template
        self.config = config
        self.pages = self.create_contexts(self._apply_filter(pages))
        self._build_page_index()

    def _apply_filter(self, pages):
        return [p for p in pages \
                if p.path.startswith(self.path) \
                and p.path.endswith('.html')]

    def contains_page(self, page):
        """Check if page is part of the collection."""
        return page.path in self.__paths

    def page_context(self, page):
        """Throws ValueError if page is not part of the collection"""
        idx = self.__paths.index(page.path)
        return self.pages[idx]

    def create_contexts(self, pages):
        contexts = []
        for page in pages:
            # Parse headers and markdown body
            headers, body = parsePost(page.data())
            # Build a context for each post
            ctx = Context()
            ctx.update(headers)
            ctx[Collection.CONTEXT_RAW_KEY] = body
            ctx['path'] = page.path
            ctx['date'] = Collection.to_datetime(headers)
            ctx['url'] = page.absolute_final_url
            for list_type in ['tags', 'category', 'topics']:
                ctx[list_type] = Collection.to_list(headers, list_type)
            contexts.append(ctx)
        return contexts

    def _build_page_index(self):
        self.__paths = []
        for ctx in self.pages:
            self.__paths.append(ctx['path'])

    @staticmethod
    def to_list(headers, key):
        if headers.get(key):
            return [h.strip() for h in headers[key].split(',')]
        return []

    @staticmethod
    def to_datetime(headers):
        return parseDate(headers.get('date') or headers.get('created'))

    def filter(self, value, key='tags'):
        return filter(lambda p: value in p.get(key), self.pages)

    def sort(self, key='date', reverse=False):
        self.pages = sorted(self.pages, key=lambda x: x[key])
        if reverse:
            self.pages.reverse()
        self._build_page_index()

    def create_navigation(self):
        indexes = range(0, len(self.pages))
        for i in indexes:
            if i+1 in indexes: self.pages[i]['prev_post'] = self.pages[i+1]
            if i-1 in indexes: self.pages[i]['next_post'] = self.pages[i-1]

    def serialize(self):
        return toDict(self.config.get('settings', {}), self.pages)

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def __iter__(self):
        return self.pages.__iter__()

    def __repr__(self):
        return '<{0}: {1} ({2} pages)>'.format(self.title, self.path, len(self.pages))


def preBuild(site):
    settings = site.config.get('settings', {})
    collections = site.config.get('collections', {})

    global COLLECTIONS
    global COLLECTIONS_JSON
    for name, conf in collections.items():
        coll = Collection(conf['title'], conf['path'], conf['template'],
                          pages=site.pages(), config=site.config)
        order = conf.get('order')
        if order:
            coll.sort(**order)
        coll.create_navigation()
        COLLECTIONS[name] = coll
        COLLECTIONS_JSON[name] = coll.serialize()

    global NEWS_JSON
    NEWS_JSON = toDict(settings,
        COLLECTIONS['blog'].filter('news', key='category'))

    global DEVELOPER_NEWS_JSON
    DEVELOPER_NEWS_JSON = toDict(settings,
        COLLECTIONS['blog'].filter('developernews', key='category'))


def preBuildPage(site, page, context, data):
    """
    Add collections to every page context so we can
    access them from wherever on the site.
    """
    for name, collection_json in COLLECTIONS_JSON.items():
        context[name+'_json'] = collection_json
    for name, collection in COLLECTIONS.items():
        context[name] = collection
        if collection.contains_page(page):
            ctx = collection.page_context(page)
            tpl = get_template(ctx.get('template', collection.template))
            raw = force_text(ctx[Collection.CONTEXT_RAW_KEY])
            ctx[Collection.CONTEXT_OUTPUT_KEY] = mark_safe(
                markdown(raw, extras=["fenced-code-blocks", "header-ids"])
            )
            context.update(ctx)
            data = tpl.render(context)

    # TODO: make this more generic!
    context['news_json'] = NEWS_JSON
    context['developer_news_json'] = DEVELOPER_NEWS_JSON

    return context, data

