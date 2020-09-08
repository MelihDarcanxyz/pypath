#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  Copyright (c) 2014-2020 - EMBL
#
#  File author(s): Dénes Türei (turei.denes@gmail.com)
#
#  This code is not for public use.
#  Please do not redistribute.
#  For permission please contact me.
#
#  Website: http://omnipathdb.org/
#

import urllib.request
import time
import itertools
import collections
import json

_urls = (
    'https://omnipathdb.org/',
    'http://localhost:33333/',
)

_queries = {
    'interactions': [
        {
            'types': (
                'post_transcriptional',
                'transcriptional',
                'post_translational',
                'mirna_transcriptional',
            ),
        },
        {
            'datasets': (
                'omnipath',
                'kinaseextra',
                'pathwayextra',
                'ligrecextra',
                'tf_target',
                'dorothea',
            ),
        },
        {
            'types': 'transcriptional',
            'datasets': 'dorothea',
            'dorothea_levels': 'A,B,C,D',
        },
    ]
}


class ServerTest(object):

    def __init__(self, outfile = None, urls = None, queries = None):

        self.outfile = outfile or (
            'omnipath-server-test-%s.tsv' % time.strftime('%Y-%m-%d %H:%M:%S')
        )
        self.urls = urls or _urls
        self.queries = queries or _queries


    def main(self):

        self.add_databases()
        self.generate_targets()
        self.retrieve()
        self.export()


    def add_databases(self):

        databases = collections.defaultdict(set)

        for url in self.urls:

            databases_url = '%sdatabases?format=json' % url

            con = urllib.request.urlopen(databases_url)

            for typ, dbs in json.loads(con.read()).items():

                databases[typ].update(set(dbs))

        for typ, dbs in databases.items():

            self.queries['interactions'].append({
                'resources': tuple(dbs),
                'types': typ,
            })


    def generate_targets(self):

        self.targets = []

        for query_type, param in self.queries.items():

            keys, values = zip(*param.items())

            values = [
                (val,) if isinstance(val, str) else val
                for val in values
            ]

            for this_values in itertools.product(values):

                this_url_param = '%s?%s' % (
                    query_type,
                    '&'.join(
                        '%s=%s' % (key, value)
                        for key, value in zip(keys, this_values)
                    ),
                )

                self.targets.append(this_url_param)


    def retrieve(self):

        self.result = []

        for target in self.targets:

            self.result.append(
                [target] +
                [
                    self.retrieve_one('%s%s' % url, target)
                    for url in self.urls
                ]
            )


    def retrieve_one(self, url):

        print('Retrieving %s' % url)

        con = urllib.request.urlopen(url)

        if content.getcode() == 200:

            content = con.read()

            if not content.startswith('Something is not'):

                return len(content.split('\n'))


    def export(self, outfile = None):

        outfile = outfile or self.outfile

        with open(outfile, 'w') as fp:

            fp.write('\t%s\n' % '\t'.join(self.urls))

            fp.write('\n'.join(
                '\t'.join(str(i) for i in line)
                for line in self.result
            ))