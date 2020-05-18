#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#
#  Copyright
#  2014-2020
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  File author(s): Dénes Türei (turei.denes@gmail.com)
#                  Nicolàs Palacio
#                  Olga Ivanova
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

from future.utils import iteritems

import sys
import os
import re
import copy
import collections
import itertools

from pypath.share import session as session_mod

_logger = session_mod.Logger(name = 'server')
_log = _logger._log

try:
    import twisted.web.resource
    import twisted.web.server
    import twisted.internet
except:
    _log('No module `twisted` available.', -1)

import urllib
import json

import pandas as pd
import numpy as np

import pypath.resources as resources
from pypath.omnipath.server import generate_about_page
import pypath.omnipath.server._html as _html
import pypath.resources.urls as urls
import pypath.share.common as common
import pypath.legacy.db_categories as db_categories
import pypath.core.intercell_annot as intercell_annot
from pypath.share.common import flat_list
from pypath._version import __version__

if 'unicode' not in __builtins__:
    unicode = str


def stop_server():

    reactor.removeAll()


class BaseServer(twisted.web.resource.Resource, session_mod.Logger):


    def __init__(self):

        if not hasattr(self, '_log_name'):

            session_mod.Logger.__init__(name = 'server')

        self._log('Initializing BaseServer.')

        self.htmls = ['info', '']
        self.welcome_message = (
            'Hello, this is the REST service of pypath %s. Welcome!\n'
            'For the descriptions of pathway resources go to `/info`.\n'
            'Available query types: interactions, enz_sub, complexes, \n'
            'annotations, intercell'
        ) % __version__

        self.isLeaf = True

        twisted.web.resource.Resource.__init__(self)
        self._log('Twisted resource initialized.')


    def render_GET(self, request):

        response = []

        request.postpath = [i.decode('utf-8') for i in request.postpath]

        self._log('Processing request: `%s`.' % request.uri.decode('utf-8'))

        html = len(request.postpath) == 0 or request.postpath[0] in self.htmls
        self._set_defaults(request, html = html)

        if (
            request.postpath and
            hasattr(self, request.postpath[0]) and
            request.postpath[0][0] != '_'
        ):

            self._process_postpath(request)

            toCall = getattr(self, request.postpath[0])

            if hasattr(toCall, '__call__'):

                response = toCall(request)
                response = (
                    response.encode('utf-8')
                    if type(response) is unicode else
                    response
                )
                response = [response]

        elif not request.postpath:

            response = [self._root(request)]

        if not response:

            response = [
                (
                    "Not found: %s%s" % (
                        '/'.join(request.postpath),
                        ''
                        if len(request.args) == 0 else
                        '?%s' %
                            '&'.join([
                                '%s=%s' % (
                                    k.decode('utf-8'),
                                    v[0].decode('utf-8')
                                )
                                for k, v in iteritems(request.args)
                                if v
                            ])
                    )
                ).encode('utf-8')
            ]

        request.write(response[0])

        self._log(
            'Finished serving request: `%s`.' % request.uri.decode('utf-8')
        )

        request.finish()

        return twisted.web.server.NOT_DONE_YET


    def render_POST(self, request):

        if (
            request.getHeader(b'content-type') and
            request.getHeader(b'content-type').startswith(b'application/json')
        ):

            args_raw = json.loads(request.content.getvalue())
            request.args = dict(
                (
                    k.encode('utf-8'),
                    [v.encode('utf-8')]
                    if type(v) is not list else
                    [','.join(v).encode('utf-8')]
                )
                for k, v in iteritems(args_raw)
            )

        return self.render_GET(request)


    def _set_defaults(self, request, html=False):

        for k, v in iteritems(request.args):

            request.args[k] = [b','.join(v)]

        request.setHeader('Cache-Control', 'Public')

        if '' in request.postpath:
            request.postpath.remove('')

        request.setHeader('Access-Control-Allow-Origin', '*')

        if html:
            request.setHeader('Content-Type', 'text/html; charset=utf-8')
        elif (
            b'format' in request.args and
            request.args[b'format'][0] == b'json'
        ):
            request.setHeader(
                'Content-Type',
                'application/json'
            )
        else:
            request.args[b'format'] = [b'text']
            request.setHeader('Content-Type', 'text/plain; charset=utf-8')

        request.args[b'header'] = (
            [b'1']
                if b'header' not in request.args else
            request.args[b'header']
        )

        request.args[b'fields'] = (
            []
                if b'fields' not in request.args else
            request.args[b'fields']
        )


    def _process_postpath(self, req):

        if len(req.postpath) > 1:

            ids_left = [req.postpath[1].encode('utf-8')]

            ids_right = (
                [req.postpath[2].encode('utf-8')]
                if (
                    len(req.postpath) > 2 and
                    req.postpath[2].lower() not in {'and', 'or'}
                ) else
                None
            )

            left_right = (
                [b'OR']
                if req.postpath[-1].lower() not in {'and', 'or'} else
                [req.postpath[-1].encode('utf-8')]
            )

            if ids_right:

                if req.postpath[0] == 'enzsub':

                    req.args[b'enzymes'] = ids_left
                    req.args[b'substrates'] = ids_right

                else:
                    req.args[b'sources'] = ids_left
                    req.args[b'targets'] = ids_right

            else:
                req.args[b'partners'] = ids_left

            if req.postpath[0] == 'enzsub':
                req.args[b'enzyme_substrate'] = left_right
            else:
                req.args[b'source_target'] = left_right


    def about(self, req):

        return self.welcome_message


    def info(self, req):

        if (
            b'format' in req.args and
            req.args[b'format'][0] == b'json' and
            hasattr(self, 'resources')
        ):

            return self.resources(req)

        rc = resources.get_controller()
        rc.update()

        return generate_about_page.generate_about_html(rc.data)


    def _root(self, req):

        return _html.main_page()


    def _parse_arg(self, arg):

        if type(arg) is list and len(arg):
            arg = arg[0]
        if hasattr(arg, 'decode'):
            arg = arg.decode('utf-8')
        if hasattr(arg, 'isdigit') and arg.isdigit():
            arg = int(arg)
        if arg == 'no':
            arg = False
        if arg == 'yes':
            arg = True

        return bool(arg)


class TableServer(BaseServer):

    query_types = {
        'annotations',
        'intercell',
        'interactions',
        'enzsub',
        'ptms',
        'complexes',
        'about',
        'info',
        'queries',
        'annotations_summary',
        'intercell_summary',
    }
    data_query_types = {
        'annotations',
        'intercell',
        'interactions',
        'enzsub',
        'complexes',
    }
    list_fields = {
        'sources',
        'references',
        'isoforms',
    }

    int_list_fields = {
        'references',
        'isoforms',
    }

    args_reference = {
        'interactions': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table'
            },
            'datasets': {
                'omnipath',
                'tfregulons',
                'dorothea',
                'tf_target',
                'kinaseextra',
                'ligrecextra',
                'pathwayextra',
                'mirnatarget',
            },
            'types': {
                'post_translational',
                'transcriptional',
                'post_transcriptional',
            },
            'sources':  None,
            'targets':  None,
            'partners': None,
            'genesymbols': {'1', '0', 'no', 'yes'},
            'fields': {
                'entity_type',
                'references',
                'sources',
                'tfregulons_level',
                'tfregulons_curated',
                'tfregulons_chipseq',
                'tfregulons_tfbs',
                'tfregulons_coexp',
                'dorothea_level',
                'dorothea_curated',
                'dorothea_chipseq',
                'dorothea_tfbs',
                'dorothea_coexp',
                'type',
                'ncbi_tax_id',
                'databases',
                'organism',
                'curation_effort',
            },
            'tfregulons_levels':  {'A', 'B', 'C', 'D', 'E'},
            'tfregulons_methods': {
                'curated',
                'chipseq',
                'coexp',
                'tfbs',
            },
            'dorothea_levels':  {'A', 'B', 'C', 'D', 'E'},
            'dorothea_methods': {
                'curated',
                'chipseq',
                'coexp',
                'tfbs',
            },
            'organisms': {
                '9606',
                '10090',
                '10116',
            },
            'databases': None,
            'source_target': {
                'AND',
                'OR',
                'and',
                'or',
            },
            'directed': {'1', '0', 'no', 'yes'},
            'signed': {'1', '0', 'no', 'yes'},
            'entity_types': {
                'protein',
                'complex',
                'mirna',
                'lncrna',
                'small_molecule',
            },
        },
        'enzsub': {
            'header':      None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'enzymes':     None,
            'substrates':  None,
            'partners':    None,
            'genesymbols': {'1', '0', 'no', 'yes'},
            'organisms': {
                '9606',
                '10090',
                '10116',
            },
            'databases': None,
            'residues':  None,
            'modification': None,
            'types': None,
            'fields': {
                'sources',
                'references',
                'ncbi_tax_id',
                'organism',
                'databases',
                'isoforms',
                'curation_effort',
            },
            'enzyme_substrate': {
                'AND',
                'OR',
                'and',
                'or',
            }
        },
        'annotations': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'databases': None,
            'proteins': None,
            'fields': None,
            'genesymbols': {'1', '0', 'no', 'yes'},
            'entity_types': {
                'protein',
                'complex',
                'mirna',
                'lncrna',
                'small_molecule',
            },
        },
        'annotations_summary': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'databases': None,
            'fields': None,
            'cytoscape': {'1', '0', 'no', 'yes'},
        },
        'intercell': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'scope': {
                'specific',
                'generic',
            },
            'aspect': {
                'functional',
                'locational',
            },
            'source': {
                'resource_specific',
                'composite',
            },
            'categories': None,
            'parent': None,
            'proteins': None,
            'fields': None,
            'entity_types': {
                'protein',
                'complex',
                'mirna',
                'lncrna',
                'small_molecule',
            },
            'transmitter': {'1', '0', 'no', 'yes'},
            'receiver': {'1', '0', 'no', 'yes'},
            'trans': {'1', '0', 'no', 'yes'},
            'rec': {'1', '0', 'no', 'yes'},
            'secreted': {'1', '0', 'no', 'yes'},
            'plasma_membrane_peripheral': {'1', '0', 'no', 'yes'},
            'plasma_membrane_transmembrane': {'1', '0', 'no', 'yes'},
            'sec': {'1', '0', 'no', 'yes'},
            'pmp': {'1', '0', 'no', 'yes'},
            'pmtm': {'1', '0', 'no', 'yes'},
        },
        'intercell_summary': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'scope': {
                'specific',
                'generic',
            },
            'aspect': {
                'functional',
                'locational',
            },
            'source': {
                'resource_specific',
                'generic',
            },
            'categories': None,
            'parent': None,
            'fields': None,
            'transmitter': {'1', '0', 'no', 'yes'},
            'receiver': {'1', '0', 'no', 'yes'},
            'trans': {'1', '0', 'no', 'yes'},
            'rec': {'1', '0', 'no', 'yes'},
            'secreted': {'1', '0', 'no', 'yes'},
            'plasma_membrane_peripheral': {'1', '0', 'no', 'yes'},
            'plasma_membrane_transmembrane': {'1', '0', 'no', 'yes'},
            'sec': {'1', '0', 'no', 'yes'},
            'pmp': {'1', '0', 'no', 'yes'},
            'pmtm': {'1', '0', 'no', 'yes'},
        },
        'complexes': {
            'header': None,
            'format': {
                'json',
                'tab',
                'text',
                'tsv',
                'table',
            },
            'databases': None,
            'proteins': None,
            'fields': None,
        },
        'resources': {
            'format': {
                'json',
            },
            'datasets': {
                'interactions',
                'interaction',
                'network',
                'enz_sub',
                'enzyme-substrate',
                'annotations',
                'annotation',
                'annot',
                'intercell',
                'complex',
                'complexes',
            },
            'subtypes': None,
        },
    }


    query_type_synonyms = {
        'interactions': 'interactions',
        'interaction': 'interactions',
        'network': 'interactions',
        'enz_sub': 'enzsub',
        'ptms': 'enzsub',
        'ptm': 'enzsub',
        'enzyme-substrate': 'enzsub',
        'enzyme_substrate': 'enzsub',
        'annotations': 'annotations',
        'annotation': 'annotations',
        'annot': 'annotations',
        'intercell': 'intercell',
        'intercellular': 'intercell',
        'inter_cell': 'intercell',
        'inter-cell': 'intercell',
        'complex': 'complexes',
        'complexes': 'complexes',
    }
    datasets_ = {
        'omnipath',
        'tfregulons',
        'dorothea',
        'tf_target',
        'kinaseextra',
        'ligrecextra',
        'pathwayextra',
        'mirnatarget',
    }
    dorothea_methods = {'curated', 'coexp', 'chipseq', 'tfbs'}
    dataset2type = {
        'omnipath': 'post_translational',
        'tfregulons': 'transcriptional',
        'dorothea': 'transcriptional',
        'tf_target': 'transcriptional',
        'kinaseextra': 'post_translational',
        'ligrecextra': 'post_translational',
        'pathwayextra': 'post_translational',
        'mirnatarget': 'post_transcriptional'
    }
    interaction_fields = {
        'references', 'sources', 'dorothea_level',
        'dorothea_curated', 'dorothea_chipseq',
        'dorothea_tfbs', 'dorothea_coexp',
        'tfregulons_level', 'tfregulons_curated',
        'tfregulons_chipseq', 'tfregulons_tfbs', 'tfregulons_coexp',
        'type', 'ncbi_tax_id', 'databases', 'organism',
        'curation_effort',
    }
    enzsub_fields = {
        'references', 'sources', 'databases',
        'isoforms', 'organism', 'ncbi_tax_id',
        'curation_effort',
    }
    default_input_files = {
        'interactions': 'omnipath_webservice_interactions.tsv',
        'enzsub': 'omnipath_webservice_enz_sub.tsv',
        'annotations': 'omnipath_webservice_annotations.tsv',
        'complexes': 'omnipath_webservice_complexes.tsv',
        'intercell': 'omnipath_webservice_intercell.tsv',
    }
    default_dtypes = collections.defaultdict(
        dict,
        interactions = {
            'source': 'category',
            'target': 'category',
            'source_genesymbol': 'category',
            'target_genesymbol': 'category',
            'is_directed': 'int8',
            'is_stimulation': 'int8',
            'is_inhibition': 'int8',
            'consensus_direction': 'int8',
            'consensus_stimulation': 'int8',
            'consensus_inhibition': 'int8',
            'sources': 'category',
            'references': 'category',
            'dip_url': 'category',
            'dorothea_curated': 'category',
            'dorothea_chipseq': 'category',
            'dorothea_tfbs': 'category',
            'dorothea_coexp': 'category',
            'dorothea_level': 'category',
            'type': 'category',
            'ncbi_tax_id_source': 'int16',
            'ncbi_tax_id_target': 'int16',
            'entity_type_source': 'category',
            'entity_type_target': 'category',
            'curation_effort': 'int16',
        },
        annotations = {
            'uniprot': 'category',
            'genesymbol': 'category',
            'entity_type': 'category',
            'source': 'category',
            'label': 'category',
            'value': 'category',
            'record_id': 'uint32',
        },
        enzsub = {
            'enzyme': 'category',
            'substrate': 'category',
            'enzyme_genesymbol': 'category',
            'substrate_genesymbol': 'category',
            'isoforms': 'category',
            'residue_type': 'category',
            'residue_offset': 'uint16',
            'modification': 'category',
            'sources': 'category',
            'references': 'category',
            'ncbi_tax_id': 'int16',
            'curation_effort': 'int32',
        },
        complexes = {
            'name': 'category',
            'stoichiometry': 'category',
            'sources': 'category',
            'references': 'category',
            'identifiers': 'category',
        },
        intercell = {
            'category': 'category',
            'database': 'category',
            'uniprot': 'category',
            'genesymbol': 'category',
            'parent': 'category',
            'aspect': 'category',
            'scope': 'category',
            'source': 'category',
            'entity_type': 'category',
            'transmitter': 'bool',
            'receiver': 'bool',
            'secreted': 'bool',
            'plasma_membrane_transmembrane': 'bool',
            'plasma_membrane_peripheral': 'bool',
        }
    )

    # the annotation attributes served for the cytoscape app
    cytoscape_attributes = {
        ('Zhong2015', 'type'),
        ('MatrixDB', 'mainclass'),
        ('Matrisome', ('mainclass', 'subclass', 'subsubclass')),
        # ('TFcensus', 'in TFcensus'),
        ('Locate', ('location', 'cls')),
        (
            'Phosphatome',
            (
                'family',
                'subfamily',
                #'has_protein_substrates',
            )
        ),
        ('CancerSEA', 'state'),
        ('GO_Intercell', 'mainclass'),
        ('Adhesome', 'mainclass'),
        ('SignaLink3', 'pathway'),
        (
            'HPA_secretome',
            (
                'mainclass',
                #'secreted',
            )
        ),
        (
            'OPM',
            (
                'membrane',
                'family',
                #'transmembrane',
            )
        ),
        ('KEGG', 'pathway'),
        #(
            #'CellPhoneDB',
            #(
                ## 'receptor',
                ## 'peripheral',
                ## 'secreted',
                ## 'transmembrane',
                ## 'receptor_class',
                ## 'secreted_class',
            #)
        #),
        ('kinase.com', ('group', 'family', 'subfamily')),
        ('Membranome', ('membrane',)),
        #('CSPA', 'in CSPA'),
        #('MSigDB', 'geneset'),
        #('Integrins', 'in Integrins'),
        ('HGNC', 'mainclass'),
        ('CPAD', ('pathway', 'effect_on_cancer', 'cancer', )),
        ('Signor', 'pathway'),
        ('Ramilowski2015', 'mainclass'),
        ('HPA_subcellular', 'location'),
        #('DisGeNet', 'disease'),
        ('Surfaceome', ('mainclass', 'subclasses')),
        ('IntOGen', 'role'),
        ('HPMR', ('role', 'mainclass', 'subclass', 'subsubclass')),
        #('CancerGeneCensus',
            #(
                ##'hallmark',
                ##'somatic',
                ##'germline',
                #'tumour_types_somatic',
                #'tumour_types_germline',
            #)
        #),
        #('DGIdb', 'category'),
        ('ComPPI', 'location'),
        ('Exocarta', 'vesicle'),
        ('Vesiclepedia', 'vesicle'),
        ('Ramilowski_location', 'location'),
        ('LRdb', ('role', 'cell_type')),
    }

    def __init__(
            self,
            input_files = None,
            only_tables = None,
            exclude_tables = None,
        ):
        """
        Server based on ``pandas`` data frames.

        :param dict input_files:
            Paths to tables exported by the ``pypath.websrvtab`` module.
        """

        session_mod.Logger.__init__(self, name = 'server')

        self._log('TableServer starting up.')

        self.input_files = copy.deepcopy(self.default_input_files)
        self.input_files.update(input_files or {})
        self.data = {}

        self.to_load = (
            self.data_query_types - common.to_set(exclude_tables)
                if only_tables is None else
            common.to_set(only_tables)
        )

        self._log('Datasets to load: %s.' % (', '.join(sorted(self.to_load))))

        self._read_tables()

        self._preprocess_interactions()
        self._preprocess_enzsub()
        self._preprocess_annotations()
        self._preprocess_complexes()
        self._preprocess_intercell()
        self._update_databases()

        BaseServer.__init__(self)
        self._log('TableServer startup ready.')


    def _read_tables(self):

        self._log('Loading data tables.')

        for name, fname in iteritems(self.input_files):

            if name not in self.to_load:

                continue

            self._log('Loading dataset `%s` from file `%s`.' % (name, fname))

            if not os.path.exists(fname):

                self._log(
                    'Missing table: `%s`.' % fname
                )
                continue

            dtype = self.default_dtypes[name]

            self.data[name] = pd.read_csv(
                fname,
                sep = '\t',
                index_col = False,
                dtype = dtype,
            )

            self._log(
                'Table `%s` loaded from file `%s`.' % (name, fname)
            )


    def _network(self, req):

        hdr = ['nodes', 'edges', 'is_directed', 'sources']
        tbl = self.data['network'].field
        val = dict(zip(tbl.field, tbl.value))

        if b'format' in req.args and req.args[b'format'] == b'json':
            return json.dumps(val)
        else:
            return '%s\n%s' % ('\t'.join(hdr), '\t'.join(
                [str(val[h]) for h in hdr]))


    def _preprocess_interactions(self):

        if 'interactions' not in self.data:

            return

        self._log('Preprocessing interactions.')
        tbl = self.data['interactions']
        tbl['set_sources'] = pd.Series(
            [set(s.split(';')) for s in tbl.sources]
        )
        tbl['set_dorothea_level'] = pd.Series(
            [
                set(s.split(';'))
                if not pd.isnull(s) else
                set([])
                for s in tbl.dorothea_level
            ]
        )


    def _preprocess_enzsub(self):

        if 'enzsub' not in self.data:

            return

        self._log('Preprocessing enzyme-substrate relationships.')
        tbl = self.data['enzsub']
        tbl['set_sources'] = pd.Series(
            [set(s.split(';')) for s in tbl.sources]
        )


    def _preprocess_complexes(self):

        if 'complexes' not in self.data:

            return

        self._log('Preprocessing complexes.')
        tbl = self.data['complexes']
        tbl['set_sources'] = pd.Series(
            [set(s.split(';')) for s in tbl.sources]
        )
        tbl['set_proteins'] = pd.Series(
            [set(c.split('_')) for c in tbl.components]
        )


    def _preprocess_annotations_old(self):

        if 'annotations' not in self.data:

            return

        renum = re.compile(r'[-\d\.]+')


        def _agg_values(vals):

            result = (
                '#'.join(sorted(set(str(ii) for ii in vals)))
                if not all(
                    isinstance(i, (int, float)) or (
                        isinstance(i, str) and
                        i and (
                            i is None or
                            renum.match(i)
                        )
                    )
                    for i in vals
                ) else
                '<numeric>'
            )

            return result


        self._log('Preprocessing annotations.')

        self.data['annotations_summary'] = self.data['annotations'].groupby(
            ['source', 'label'],
        ).agg({'value': _agg_values}).reset_index(drop = False)


    def _preprocess_annotations(self):

        if 'annotations' not in self.data:

            return

        renum = re.compile(r'[-\d\.]+')


        self._log('Preprocessing annotations.')

        values_by_key = collections.defaultdict(set)

        # we need to do it this way as we are memory limited on the server
        # and pandas groupby is very memory intensive
        for row in self.data['annotations'].itertuples():

            value = (
                '<numeric>'
                if (
                    (
                        not isinstance(row.value, bool) and
                        isinstance(row.value, (int, float))
                    ) or
                    renum.match(row.value)
                ) else
                str(row.value)
            )

            values_by_key[(row.source, row.label)].add(value)

        for vals in values_by_key.values():

            if len(vals) > 1:

                vals.discard('<numeric>')

            vals.discard('')
            vals.discard('nan')

        self.data['annotations_summary'] = pd.DataFrame(
            list(
                (source, label, '#'.join(sorted(values)))
                for (source, label), values in iteritems(values_by_key)
            ),
            columns = ['source', 'label', 'value'],
        )


    def _preprocess_intercell(self):

        if 'intercell' not in self.data:

            return

        self._log('Preprocessing intercell data.')
        tbl = self.data['intercell']
        tbl.drop('full_name', axis = 1, inplace = True, errors = 'ignore')
        self.data['intercell_summary'] = tbl.groupby(
            ['category', 'parent', 'database'],
            as_index = False,
        ).agg({})


    def _update_databases(self):

        self._databases_dict = collections.defaultdict(dict)

        for query_type in self.data_query_types:

            if query_type not in self.data:

                continue

            tbl = self.data[query_type]

            for colname, argname in (
                ('database', 'databases'),
                ('sources', 'databases'),
                ('source', 'databases'),
                ('category', 'categories')
            ):

                if colname in tbl.columns:

                    break

            values = sorted(set(
                itertools.chain(*(
                    val.split(';') for val in getattr(tbl, colname)
                ))
            ))

            for db in values:

                if 'datasets' not in self._databases_dict[db]:

                    self._databases_dict[db]['datasets'] = {}

                if query_type not in self._databases_dict[db]['datasets']:

                    self._databases_dict[db]['datasets'][query_type] = (

                        {'classes': {}}

                            if query_type == 'intercell' else

                        sorted(db_categories.get_categories(db, names = True))

                            if query_type == 'interactions' else

                        []

                    )

            self.args_reference[query_type][argname] = values

        self._databases_dict = dict(self._databases_dict)


    def _check_args(self, req):

        result = []
        ref = self.args_reference[req.postpath[0]]

        for arg, val in iteritems(req.args):

            arg = arg.decode('utf-8')

            if arg in ref:

                if not ref[arg] or not val:

                    continue

                val = (
                    {val[0]}
                    if type(val[0]) is int else
                    set(val[0].decode('utf-8').split(','))
                )

                unknowns = val - set(ref[arg])

                if unknowns:

                    result.append(
                        ' ==> Unknown values for argument `%s`: `%s`' % (
                            arg,
                            ', '.join(str(u) for u in unknowns)
                        )
                    )

            else:

                result.append(' ==> Unknown argument: `%s`' % arg)

        req.args[b'header'] = self._parse_arg(req.args[b'header'])

        if result:

            return (
                'Something is not entirely good:\n%s\n\n'
                'Please check the examples at\n'
                'https://github.com/saezlab/pypath\n'
                'and\n'
                'https://github.com/saezlab/DoRothEA\n'
                'If you still experiencing issues contact us at\n'
                'https://github.com/saezlab/pypath/issues'
                '' % '\n'.join(result)
            )


    def _query_type(self, query_type):

        return (
            self.query_type_synonyms[query_type]
                if query_type in self.query_type_synonyms else
            query_type
        )


    def queries(self, req):

        query_type = (
            req.postpath[1]
                if len(req.postpath) > 1 else
            'interactions'
        )

        query_type = self._query_type(query_type)

        query_param = (
            req.postpath[2]
                if len(req.postpath) > 2 else
            None
        )

        if query_type in self.args_reference:

            result = self.args_reference[query_type]

            if query_param is not None and query_param in result:

                result = {}
                result[query_param] = (
                    self.args_reference[query_type][query_param]
                )

        else:

            result = {}
            result[query_type] = (
                'No possible arguments defined for'
                'query `%s` or no such query available.' % query_type
            )

        if b'format' in req.args and req.args[b'format'][0] == b'json':

            return json.dumps(result)

        else:

            return 'argument\tvalues\n%s' % '\n'.join(
                '%s\t%s' % (
                    k,
                    ';'.join(v)
                        if isinstance(v, (list, set, tuple)) else
                    str(v)
                )
                for k, v in iteritems(result)
            )


    def databases(self, req):

        query_type = (
            req.postpath[1]
                if len(req.postpath) > 1 else
            'interactions'
        )

        query_type = self._query_type(query_type)

        datasets = (
            set(req.postpath[2].split(','))
                if len(req.postpath) > 2 else
            None
        )

        tbl = (
            self.data[query_type]
                if query_type in self.data else
            self.data['interactions']
        )

        # filter for datasets
        if query_type == 'interactions':

            if datasets is not None:

                tbl = tbl[tbl.type.isin(datasets)]

            else:

                datasets = self._get_datasets()

            result = {}

            for dataset in datasets:

                result[dataset] = sorted(set.union(
                    *tbl[tbl.type == dataset].set_sources)
                )

        else:

            result = {}
            result['*'] = sorted(set.union(*tbl.set_sources))

        if b'format' in req.args and req.args[b'format'][0] == b'json':

            return json.dumps(result)

        else:

            return 'dataset\tdatabases\n%s' % '\n'.join(
                '%s\t%s' % (k, ';'.join(v)) for k, v in iteritems(result)
            )


    def _get_datasets(self):

        return list(self.data['interactions'].type.unique())


    def datasets(self, req):

        query_type = (
            req.postpath[1]
                if len(req.postpath) > 1 else
            'interactions'
        )

        if query_type == 'interactions':

            result = self._get_datasets()

        else:

            result = []

        if b'format' in req.args and req.args[b'format'][0] == b'json':

            return json.dumps(result)

        else:

            return ';'.join(result)


    def interactions(
            self,
            req,
            datasets  = {'omnipath'},
            databases = None,
            dorothea_levels = {'A', 'B'},
            organisms = {9606},
            source_target = 'OR'
        ):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        hdr = [
            'source',
            'target',
            'is_directed',
            'is_stimulation',
            'is_inhibition',
            'consensus_direction',
            'consensus_stimulation',
            'consensus_inhibition',
            'dip_url',
        ]

        if b'source_target' in req.args:

            source_target = (
                req.args[b'source_target'][0].decode('utf-8').upper()
            )

        # changes the old, "tfregulons" names to new "dorothea"
        self._tfregulons_dorothea(req)

        args = {}

        for arg in (
            'datasets',
            'types',
            'sources',
            'targets',
            'partners',
            'databases',
            'organisms',
            'dorothea_levels',
            'dorothea_methods',
        ):

            args[arg] = self._args_set(req, arg)

        # if user requested TF type interactions
        # they likely want the tfregulons dataset
        if 'transcriptional' in args['types']:

            args['datasets'].add('dorothea')
            args['datasets'].add('tf_target')

        if 'post_transcriptional' in args['types']:

            args['datasets'].add('mirnatarget')

        # here adjust on the defaults otherwise we serve empty
        # response by default
        args['datasets'] = args['datasets'] or datasets
        args['datasets'] = args['datasets'] & self.datasets_

        args['organisms'] = set(
            int(t) for t in args['organisms'] if t.isdigit()
        )
        args['organisms'] = args['organisms'] or organisms

        # do not allow impossible values
        # those would result KeyError later
        args['dorothea_levels'] = (
            args['dorothea_levels'] or
            dorothea_levels
        )
        args['dorothea_methods'] = (
            args['dorothea_methods'] & self.dorothea_methods
        )

        # provide genesymbols: yes or no
        if (
            b'genesymbols' in req.args and
            self._parse_arg(req.args[b'genesymbols'])
        ):
            genesymbols = True
            hdr.insert(2, 'source_genesymbol')
            hdr.insert(3, 'target_genesymbol')
        else:
            genesymbols = False

        # if user requested TF Regulons they likely want us
        # to serve TF-target interactions
        # but if they requested other types, then we
        # serve those as well
        if 'dorothea' in args['datasets'] or 'tf_target' in args['datasets']:

            args['types'].add('transcriptional')

        if 'mirnatarget' in args['datasets']:

            args['types'].add('post_transcriptional')

        # if no types provided we collect the types
        # for the datasets requested
        # or by default only the 'omnipath' dataset
        # which belongs to the 'PPI' type
        if not args['types'] or args['datasets']:

            args['types'].update(
                {self.dataset2type[ds] for ds in args['datasets']}
            )

        # starting from the entire dataset
        tbl = self.data['interactions']

        # filter by type
        tbl = tbl[tbl.type.isin(args['types'])]

        # if partners provided those will overwrite
        # sources and targets
        args['sources'] = args['sources'] or args['partners']
        args['targets'] = args['targets'] or args['partners']

        # then we filter by source and target
        # which matched against both standard names
        # and gene symbols
        if args['sources'] and args['targets'] and source_target == 'OR':

            tbl = tbl[
                tbl.target.isin(args['targets']) |
                tbl.target_genesymbol.isin(args['targets']) |
                tbl.source.isin(args['sources']) |
                tbl.source_genesymbol.isin(args['sources'])
            ]

        else:

            if args['sources']:
                tbl = tbl[
                    tbl.source.isin(args['sources']) |
                    tbl.source_genesymbol.isin(args['sources'])
                ]

            if args['targets']:
                tbl = tbl[
                    tbl.target.isin(args['targets']) |
                    tbl.target_genesymbol.isin(args['targets'])
                ]

        # filter by datasets
        if args['datasets']:

            tbl = tbl.query(' or '.join(args['datasets']))

        # filter by organism
        tbl = tbl[
            tbl.ncbi_tax_id_source.isin(args['organisms']) |
            tbl.ncbi_tax_id_target.isin(args['organisms'])
        ]

        # filter by DoRothEA confidence levels
        if 'transcriptional' in args['types'] and args['dorothea_levels']:

            tbl = tbl[
                np.logical_not(tbl.dorothea) |
                [
                    bool(levels & args['dorothea_levels'])
                    for levels in tbl.set_dorothea_level
                ]
            ]

        # filter by databases
        if args['databases']:

            tbl = tbl[
                [
                    bool(sources & args['databases'])
                    for sources in tbl.set_sources
                ]
            ]

         # filtering for entity types
        if b'entity_types' in req.args:

            entity_types = self._args_set(req, 'entity_types')

            tbl = tbl[
                tbl.entity_type_source.isin(entity_types) |
                tbl.entity_type_target.isin(entity_types)
            ]

        # filtering by DoRothEA methods
        if 'transcriptional' in args['types'] and args['dorothea_methods']:

            q = ['dorothea_%s' % m for m in args['dorothea_methods']]

            tbl = tbl[
                tbl[q].any(1) |
                np.logical_not(tbl.dorothea)
            ]

        # filter directed & signed
        if (
            b'directed' not in req.args or
            self._parse_arg(req.args[b'directed'])
        ):

            tbl = tbl[tbl.is_directed == 1]

        if (
            b'signed' in req.args and
            self._parse_arg(req.args[b'signed'])
        ):

            tbl = tbl[np.logical_or(
                tbl.is_stimulation == 1,
                tbl.is_inhibition == 1
            )]

        if req.args[b'fields']:

            _fields = [
                f for f in
                req.args[b'fields'][0].decode('utf-8').split(',')
                if f in self.interaction_fields
            ]

            for f in _fields:

                if f == 'ncbi_tax_id' or f == 'organism':

                    hdr.append('ncbi_tax_id_source')
                    hdr.append('ncbi_tax_id_target')

                elif f == 'entity_type':

                    hdr.append('entity_type_source')
                    hdr.append('entity_type_target')

                elif f == 'databases':

                    hdr.append('sources')

                else:

                    hdr.append(f)

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def _tfregulons_dorothea(self, req):

        for arg in (b'datasets', b'fields'):

            if arg in req.args:

                req.args[arg] = (
                    req.args[arg].replace(b'tfregulons', b'dorothea')
                )

        for postfix in (b'levels', b'methods'):

            key = b'tfregulons_%s' % postfix
            new_key = b'dorothea_%s' % postfix

            if key in req.args and new_key not in req.args:

                req.args[new_key] = req.args[key]
                _ = req.args.pop(key)


    def enzsub(
            self,
            req,
            organisms = {9606},
            enzyme_substrate = 'OR'
        ):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        hdr = [
            'enzyme', 'substrate', 'residue_type',
            'residue_offset', 'modification'
        ]

        if b'enzyme_substrate' in req.args:

            enzyme_substrate = (
                req.args[b'enzyme_substrate'][0].decode('utf-8').upper()
            )

        args = {}

        for arg in (
            'enzymes', 'substrates', 'partners',
            'databases', 'organisms', 'types',
            'residues'
        ):

            args[arg] = self._args_set(req, arg)

        args['organisms'] = set(
            int(t) for t in args['organisms'] if t.isdigit()
        )
        args['organisms'] = args['organisms'] or organisms

        # provide genesymbols: yes or no
        if (
            b'genesymbols' in req.args and
            self._parse_arg(req.args[b'genesymbols'])
        ):
            genesymbols = True
            hdr.insert(2, 'enzyme_genesymbol')
            hdr.insert(3, 'substrate_genesymbol')
        else:
            genesymbols = False

        # starting from the entire dataset
        tbl = self.data['enzsub']

        # filter by type
        if args['types']:
            tbl = tbl[tbl.modification.isin(args['types'])]

        # if partners provided those will overwrite
        # enzymes and substrates
        args['enzymes'] = args['enzymes'] or args['partners']
        args['substrates'] = args['substrates'] or args['partners']

        # then we filter by enzyme and substrate
        # which matched against both standard names
        # and gene symbols
        if (
            args['enzymes'] and
            args['substrates'] and
            enzyme_substrate == 'OR'
        ):

            tbl = tbl[
                tbl.substrate.isin(args['substrates']) |
                tbl.substrate_genesymbol.isin(args['substrates']) |
                tbl.enzyme.isin(args['enzymes']) |
                tbl.enzyme_genesymbol.isin(args['enzymes'])
            ]

        else:

            if args['enzymes']:
                tbl = tbl[
                    tbl.enzyme.isin(args['enzymes']) |
                    tbl.enzyme_genesymbol.isin(args['enzymes'])
                ]

            if args['substrates']:
                tbl = tbl[
                    tbl.substrate.isin(args['substrates']) |
                    tbl.substrate_genesymbol.isin(args['substrates'])
                ]

        # filter by organism
        tbl = tbl[tbl.ncbi_tax_id.isin(args['organisms'])]

        # filter by databases
        if args['databases']:

            tbl = tbl[
                [
                    bool(args['databases'] & sources)
                    for sources in tbl.set_sources
                ]
            ]

        if req.args[b'fields']:

            _fields = [
                f for f in
                req.args[b'fields'][0].decode('utf-8').split(',')
                if f in self.enzsub_fields
            ]

            for f in _fields:

                if f == 'ncbi_tax_id' or f == 'organism':

                    hdr.append('ncbi_tax_id')

                elif f == 'databases':

                    hdr.append('sources')

                else:

                    hdr.append(f)

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def ptms(self, req):

        req.postpath[0] = 'enzsub'

        return self.enzsub(req)


    def annotations(self, req):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        # starting from the entire dataset
        tbl = self.data['annotations']

        hdr = tbl.columns

        # filtering for databases
        if b'databases' in req.args:

            databases = self._args_set(req, 'databases')

            tbl = tbl[tbl.source.isin(databases)]

        # filtering for entity types
        if b'entity_types' in req.args:

            entity_types = self._args_set(req, 'entity_types')

            tbl = tbl[tbl.entity_type.isin(entity_types)]

        # filtering for proteins
        if b'proteins' in req.args:

            proteins = self._args_set(req, 'proteins')

            tbl = tbl[
                tbl.uniprot.isin(proteins) |
                tbl.genesymbol.isin(proteins)
            ]

        # provide genesymbols: yes or no
        if (
            b'genesymbols' in req.args and
            self._parse_arg(req.args[b'genesymbols'])
        ):
            genesymbols = True
            hdr.insert(1, 'genesymbol')
        else:
            genesymbols = False

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def annotations_summary(self, req):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        # starting from the entire dataset
        tbl = self.data['annotations_summary']

        hdr = tbl.columns

        # filtering for databases
        if b'databases' in req.args:

            databases = self._args_set(req, 'databases')

            tbl = tbl[tbl.source.isin(databases)]

        if (
            b'cytoscape' in req.args and
            self._parse_arg(req.args[b'cytoscape'])
        ):

            cytoscape = True

        else:

            cytoscape = False

        tbl = tbl.loc[:,hdr]

        if cytoscape:

            tbl = tbl.set_index(['source', 'label'], drop = False)

            cytoscape_keys = {
                (source, label)
                for source, labels in self.cytoscape_attributes
                for label in (
                    labels if isinstance(labels, tuple) else (labels,)
                )
            } & set(tbl.index)

            tbl = tbl.loc[list(cytoscape_keys)]

        return self._serve_dataframe(tbl, req)


    def intercell(self, req):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        # starting from the entire dataset
        tbl = self.data['intercell']

        hdr = tbl.columns

        # filtering for category types
        for var in (
            'aspect',
            'source',
            'scope',
            'transmitter',
            'receiver',
            'parent',
        ):

            if var.encode('ascii') in req.args:

                values = self._args_set(req, var)

                tbl = tbl[getattr(tbl, var).isin(values)]

        for (_long, short) in (
            ('transmitter', 'trans'),
            ('receiver', 'rec'),
            ('secreted', 'sec'),
            ('plasma_membrane_peripheral', 'pmp'),
            ('plasma_membrane_transmembrane', 'pmtm'),
        ):

            this_arg = None
            _long_b = _long.encode('ascii')
            short_b = short.encode('ascii')

            if _long_b in req.args:

                this_arg = self._parse_arg(req.args[_long_b])

            elif short_b in req.args:

                this_arg = self._parse_arg(req.args[short_b])

            if this_arg is not None:

                tbl = tbl[getattr(tbl, _long) == this_arg]

        # filtering for categories
        if b'categories' in req.args:

            categories = self._args_set(req, 'categories')

            tbl = tbl[tbl.category.isin(categories)]

        # filtering for entity types
        if b'entity_types' in req.args:

            entity_types = self._args_set(req, 'entity_types')

            tbl = tbl[tbl.entity_type.isin(entity_types)]

        # filtering for proteins
        if b'proteins' in req.args:

            proteins = self._args_set(req, 'proteins')

            tbl = tbl[
                np.logical_or(
                    tbl.uniprot.isin(proteins),
                    tbl.genesymbol.isin(proteins),
                )
            ]

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def intercell_summary(self, req):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        # starting from the entire dataset
        tbl = self.data['intercell_summary']

        hdr = tbl.columns

        # filtering for category level
        if b'levels' in req.args:

            levels = self._args_set(req, 'levels')

            tbl = tbl[tbl.class_type.isin(levels)]

        # filtering for categories
        if b'categories' in req.args:

            categories = self._args_set(req, 'categories')

            tbl = tbl[tbl.mainclass.isin(categories)]

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def complexes(self, req):

        bad_req = self._check_args(req)

        if bad_req:

            return bad_req

        # starting from the entire dataset
        tbl = self.data['complexes']

        hdr = list(tbl.columns)
        hdr.remove('set_sources')
        hdr.remove('set_proteins')

        # filtering for databases
        if b'databases' in req.args:

            databases = self._args_set(req, 'databases')

            tbl = tbl[
                [
                    bool(sources & databases)
                    for sources in tbl.set_sources
                ]
            ]

        # filtering for proteins
        if b'proteins' in req.args:

            proteins = self._args_set(req, 'proteins')

            tbl = tbl[
                [
                    bool(this_proteins & proteins)
                    for this_proteins in tbl.set_proteins
                ]
            ]

        tbl = tbl.loc[:,hdr]

        return self._serve_dataframe(tbl, req)


    def resources(self, req):

        datasets = (

            {
                self._query_type(dataset.decode('ascii'))
                for dataset in req.args[b'datasets']
            }

            if b'datasets' in req.args else

            None

        )

        return json.dumps(
            dict(
                (k, v)
                for k, v in iteritems(self._databases_dict)
                if not datasets or datasets & set(v['datasets'].keys())
            )
        )


    @classmethod
    def _serve_dataframe(cls, tbl, req):

        if b'format' in req.args and req.args[b'format'][0] == b'json':

            data_json = tbl.to_json(orient = 'records')
            # this is necessary because in the data frame we keep lists
            # as `;` separated strings but in json is nicer to serve
            # them as lists
            data_json = json.loads(data_json)

            for i in data_json:

                for k, v in iteritems(i):

                    if k in cls.list_fields:

                        i[k] = (
                            [
                                (
                                    int(f)
                                    if (
                                        k in cls.int_list_fields and
                                        f.isdigit()
                                    ) else
                                    f
                                )
                                for f in v.split(';')
                            ]
                            if isinstance(v, common.basestring) else
                            []
                        )

            return json.dumps(data_json)

        else:

            return tbl.to_csv(
                sep = '\t',
                index = False,
                header = bool(req.args[b'header'])
            )


    @staticmethod
    def _args_set(req, arg):

        arg = arg.encode('utf-8')

        return (
            set(req.args[arg][0].decode('utf-8').split(','))
            if arg in req.args
            else set()
        )


class Rest(object):

    def __init__(
            self,
            port,
            serverclass = TableServer,
            start = True,
            **kwargs
        ):
        """
        Runs a webserver serving a `PyPath` instance listening
        to a custom port.

        Args:
        -----
        :param int port:
            The port to listen to.
        :param str serverclass'
            The class implementing the server.
        :param **kwargs:
            Arguments for initialization of the server class.
        """

        self.port = port
        _log('Creating the server class.')
        self.server = serverclass(**kwargs)
        _log('Server class ready.')

        if start:

            _log('Starting the twisted server.')
            self.start()

    def start(self):

        self.site = twisted.web.server.Site(self.server)
        _log('Site created.')
        twisted.internet.reactor.listenTCP(self.port, self.site)
        _log('Server going to listen on port %u from now.' % self.port)
        twisted.internet.reactor.run()
