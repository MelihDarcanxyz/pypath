#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#
#  Copyright
#  2014-2019
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  File author(s): Dénes Türei (turei.denes@gmail.com)
#                  Nicolàs Palacio
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

from future.utils import iteritems
from past.builtins import xrange, range, reduce

import os
import sys
import codecs
import re
import imp
import copy
import itertools
import collections

import urllib

if not hasattr(urllib, 'urlencode'):
    _urllib = urllib
    urllib = _urllib.parse

import json
try:
    import cPickle as pickle
except:
    import pickle

import timeloop

# from pypath:
import pypath.progress as progress
import pypath.common as common
import pypath.cache as cache_mod
import pypath.maps as maps
import pypath.urls as urls
import pypath.curl as curl
import pypath.mapping_input as mapping_input
import pypath.uniprot_input as uniprot_input
import pypath.input_formats as input_formats
import pypath.settings as settings
import pypath.session as session
_logger = session.get_logger()

__all__ = ['MapReader', 'MappingTable', 'Mapper']

"""
Classes for reading and use serving ID mapping data
from UniProt, file, mysql or pickle.
"""


MappingTableKey = collections.namedtuple(
    'MappingTableKey',
    [
        'name_type',
        'target_name_type',
        'ncbi_tax_id'
    ],
)
MappingTableKey.__new__.__defaults__ = ('protein', 9606)


class MapReader(session.Logger):
    """
    Reads ID translation data and creates ``MappingTable`` instances.
    When initializing ID conversion tables for the first time
    data is downloaded from UniProt and read into dictionaries.
    It takes a couple of seconds. Data is saved to pickle
    dumps, this way later the tables load much faster.
    
    :arg source_type str:
        Type of the resource, either `file`, `uniprot` or `unprotlist`.
    """
    
    def __init__(
            self,
            id_type_a,
            id_type_b,
            source_type,
            param,
            ncbi_tax_id = None,
            entity_type = None,
            uniprots = None,
            lifetime = 300,
        ):
        """
        entity_type : str
            An optional, custom string showing the type of the entities,
            e.g. `protein`. This is not mandatory for the identification
            of mapping tables, hence the same name types can't be used
            for different entities. E.g. if both proteins and miRNAs have
            Entrez gene IDs then these should be different ID types (e.g.
            `entrez_protein` and `entrez_mirna`) or both protein and miRNA
            IDs can be loaded into one mapping table and simply called
            `entrez`.
        uniprots : set
            UniProt IDs to query in case the source of the mapping table
            is the UniProt web service.
        lifetime : int
            If this table has not been used for longer than this preiod it is
            to be removed at next cleanup. Time in seconds. Passed to
            ``MappingTable``.
        """
        
        session.Logger.__init__(self, name = 'mapping')
        
        self.id_type_a = id_type_a
        self.id_type_b = id_type_b
        self.entity_type = entity_type
        self.source_type = source_type
        self.param = param
        self.lifetime = lifetime
        self.a_to_b = None
        self.b_to_a = None
        self.ncbi_tax_id = (
            ncbi_tax_id or
            param.ncbi_tax_id or
            settings.get('default_organism')
        )
        self.uniprots = uniprots
    
    
    def reload(self):
        
        modname = self.__class__.__module__
        mod = __import__(modname, fromlist = [modname.split('.')[0]])
        imp.reload(mod)
        new = getattr(mod, self.__class__.__name__)
        setattr(self, '__class__', new)
    
    
    def get_mapping_tables(self):
        """
        Returns ``MappingTable`` instances created from the already
        loaded data.
        """
        
        a_to_b = MappingTable(data = self.a_to_b, lifetime = self.lifetime)
        b_to_a = (
            MappingTable(data = self.b_to_a, lifetime = self.lifetime)
                if self.param.bi_directional else
            None
        )
        
        return a_to_b, b_to_a
    
    
    def load(self):
        
        self.use_cache = settings.get('mapping_use_cache')
        self.setup_cache()
        
        if self.use_cache and os.path.isfile(self.cachefile):
            
            self.read_cache()
        
        if (
            not self.a_to_b or (
                self.param.bi_directional and
                not self.b_to_a
            )
        ):
            
            # read from the original source
            self.read()
            
            # write cache only at successful loading
            if (
                self.a_to_b and (
                    not self.param.bi_directional or
                    self.b_to_a
                )
            ):
                
                self.write_cache()
    
    
    def write_cache(self):
        """
        Exports the ID translation data into a pickle file.
        """
        
        pickle.dump(
            (
                self.a_to_b,
                self.b_to_a,
            ),
            open(self.cachefile, 'wb')
        )
    
    
    def read_cache(self):
        """
        Reads the ID translation data from a previously saved pickle file.
        """
        
        self.a_to_b, self.b_to_a = pickle.load(open(self.cachefile, 'rb'))
    
    
    def read(self):
        """
        Reads the ID translation data from the original source.
        """
        
        if os.path.exists(self.cachefile):
            
            self._msg(
                'Removing mapping table cache file `%s`.' % self.cachefile
            )
            os.remove(self.cachefile)
        
        if source_type == "file":
            
            self.read_mapping_file()
            
        elif source_type == "uniprot":
            
            self.read_mapping_uniprot()
            
        elif source_type == "uniprotlist":
            
            self.read_mapping_uniprot_list()
    
    
    def setup_cache(self):
        """
        Constructs the cache file path as md5 hash of the parameters.
        """
        
        self.mapping_id = common.md5(
            json.dumps(
                (
                    one,
                    two,
                    self.param.bi,
                    ncbi_tax_id,
                    sorted(self.param.__dict__.items())
                )
            )
        )
        self.cachefile = os.path.join(self.cachedir, self.mapping_id)
    
    
    def set_uniprot_space(self):
        """
        Sets up a search space of UniProt IDs.
        """
        
        self.uniprots = uniprot_input.all_uniprots(
            self.ncbi_tax_id,
            swissprot = param.swissprot,
        )
    
    
    def read_mapping_file(self):
        
        if (
            not os.path.exists(param.input) and
            not hasattr(mapping_input, param.input)
        ):
            
            return {}
        
        if hasattr(mapping_input, param.input):
        
            to_call = getattr(mapping_input, param.input)
            input_args = (
                param.input_args if hasattr(param, 'input_args') else {}
            )
            infile = to_call(**input_args)
        
        else:
            
            infile = open(param.input, encoding = 'utf-8', mode = 'r')
            total = os.path.getsize(param.input)
        
        a_to_b = collections.defaultdict(set)
        b_to_a = collections.defaultdict(set)
        
        for i, line in enumerate(infile):
            
            if param.header and i < param.header:
                
                continue
            
            if hasattr(line, 'decode'):
                
                line = line.decode('utf-8')
            
            if hasattr(line, 'rstrip'):
                
                line = line.rstrip().split(param.separator)
            
            if len(line) < max(param.col_a, param.col_b):
                
                continue
            
            id_a = line[param.col_a]
            id_b = line[param.col_b]
            a_to_b[id_a].add(id_b)
            
            if param.bi_directional:
                
                b_to_a[id_b].add(id_a)
        
        if hasattr(infile, 'close'):
            
            infile.close()
        
        self.a_to_b = a_to_b
        self.b_to_a = b_to_a if self.param.bi_directional else None
    
    
    def read_mapping_uniprot_list(self):
        """
        Builds a mapping table by downloading data from UniProt's
        upload lists service.
        """
        
        a_to_b = collections.defaultdict(set)
        b_to_a = collections.defaultdict(set)
        
        if not self.uniprots:
            
            self.set_uniprot_space()
        
        if param.target_name_type != 'uniprot':
            
            u_target = self._read_mapping_uniprot_list('ACC')
            
            _ = next(u_target)
            
            ac_list = [l.split('\t')[1].strip() for l in u_target]
            
        else:
            
            ac_list = self.uniprots
        
        uniprot_data = self._read_mapping_uniprot_list(ac_list = ac_list)
        
        _ = next(uniprot_data)
        
        for l in uniprot_data:
            
            if not l:
                
                continue
            
            l = l.strip().split('\t')
            
            a_to_b[l[1]].add(l[0])

            if param.bi_directional:
                
                b_to_a[l[0]].add(l[1])
        
        self.a_to_b = a_to_b
        self.b_to_a = b_to_a if self.bi_directional else None
    
    
    def _read_mapping_uniprot_list(self, id_type_a = None, ac_list = None):
        """
        Reads a mapping table from UniProt "upload lists" service.
        """
        
        id_type_a = param.target_ac_name
        id_type_b = param.ac_name
        ac_list = ac_list or self.uniprots
        
        url = urls.urls['uniprot_basic']['lists']
        post = {
            'from': id_type_a,
            'format': 'tab',
            'to': id_type_b,
            'uploadQuery': ' '.join(sorted(ac_list)),
        }
        
        c = curl.Curl(url, post = post, large = True, silent = False)
        
        if c.result is None:
            
            for i in xrange(3):
                
                c = curl.Curl(
                    url,
                    post = post,
                    large = True,
                    silent = False,
                    cache = False,
                )
                
                if c.result is not None:
                    
                    break
        
        if c.result is None or c.fileobj.read(5) == '<!DOC':
            
            _logger.console(
                'Error at downloading ID mapping data from UniProt.', -9
            )
            
            c.result = ''
        
        c.fileobj.seek(0)
    
        return c.result
    
    
    def read_mapping_uniprot(self):
        """
        Downloads ID mappings directly from UniProt.
        See the names of possible identifiers here:
        http://www.uniprot.org/help/programmatic_access
        """
        
        resep = re.compile(r'[\s;]')
        recolend = re.compile(r'$;')
        
        a_to_b = collections.defaultdict(set)
        b_to_a = collections.defaultdict(set)
        
        
        rev = (
            ''
                if not param.swissprot else
            ' AND reviewed:%s' % param.swissprot
        )
        query = 'organism:%u%s' % (int(self.ncbi_tax_id), rev)
        
        url = urls.urls['uniprot_basic']['url']
        post = {
            'query': query,
            'format': 'tab',
            'columns': 'id,%s%s' % (
                param.field,
                '' if param.subfield is None else '(%s)' % param.subfield
            ),
        }
        
        url = '%s?%s' % (url, urllib.urlencode(post))
        c = curl.Curl(url, silent = False)
        data = c.result
        
        data = [
            [
                [xx]
                    if param.field == 'protein names' else
                [
                    xxx for xxx in resep.split(recolend.sub('', xx.strip()))
                    if len(xxx) > 0
                ]
                for xx in x.split('\t') if len(xx.strip()) > 0
            ]
            for x in data.split('\n') if len(x.strip()) > 0
        ]
        
        if data:
            
            del data[0]
            
            for l in data:
                
                if l:
                    
                    l[1] = (
                        self.process_protein_name(l[1][0])
                            if param.field == 'protein names' else
                        l[1]
                    )
                    
                    for other in l[1]:
                        
                        a_to_b[other].add(l[0][0])
                        
                        if param.bi_directional:
                            
                            b_to_a[l[0][0]].add(other)
        
        self.a_to_b = a_to_b
        self.b_to_a = b_to_a if self.bi_directional else None
    
    
    @staticmethod
    def process_protein_name(name):
        
        rebr = re.compile(r'\(([^\)]{3,})\)')
        resq = re.compile(r'\[([^\]]{3,})\]')
        
        names = [name.split('(')[0]]
        names += rebr.findall(name)
        others = flatList([x.split(';') for x in resq.findall(name)])
        others = [x.split(':')[1] if ':' in x else x for x in others]
        others = [x.split('(')[1] if '(' in x else x for x in others]
        names += others
        
        return {x.strip() for x in names}


class MappingTable(session.Logger):
    """
    This is the class directly handling ID translation data.
    It does not care about loading it or what kind of IDs these
    only accepts the translation dictionary.
    
    lifetime : int
        If this table has not been used for longer than this preiod it is
        to be removed at next cleanup. Time in seconds.
    """
    
    def __init__(
            self,
            data,
            lifetime = 30,
        ):
        
        session.Logger.__init__(self, name = 'mapping')
        
        self.data = data
        self.lifetime = lifetime
        self._used()
    
    
    def reload(self):
        
        modname = self.__class__.__module__
        mod = __import__(modname, fromlist = [modname.split('.')[0]])
        imp.reload(mod)
        new = getattr(mod, self.__class__.__name__)
        setattr(self, '__class__', new)
    
    
    def __getitem__(self, key):
        
        self._used()
        
        if key in self.data:
            
            return data[key]
        
        return set()
    
    
    def _used(self):
        
        self._last_used = time.time()
    
    
    def _expired(self):
        
        return time.time() - self._last_used > self.lifetime


class Mapper(session.Logger):

    def __init__(
            self,
            ncbi_tax_id = None,
            cleanup_period = 30,
            lifetime = 30,
        ):
        """
        cleanup_period : int
            Periodically check and remove unused mapping data.
            Time in seconds. If `None` tables kept forever.
        lifetime : int
            If a table has not been used for longer than this preiod it is
            to be removed at next cleanup.
        """
        
        session.Logger.__init__(self, name = 'mapping')
        
        self.reuniprot = re.compile(
            r'[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]'
            r'([A-Z][A-Z0-9]{2}[0-9]){1,2}'
        )
        self.cachedir = cache_mod.get_cachedir()
        self.ncbi_tax_id = ncbi_tax_id or settings.get('default_organism')
        
        self.unmapped = []
        self.data = {}
        self.uniprot_mapped = []
        self.trace = []
        self.uniprot_list_names = {
            'uniprot_id': 'UniProtKB-ID',
            'embl': 'EMBL-CDS',
            'embl_id': 'EMBL',
            'entrez': 'GeneID',
            'gi': 'GI',
            'refseqp': 'RefSeq',
            'refseqn': 'RefSeq_NT',
            'ensembl': 'Ensembl',
            'ensg': 'ENSEMBL',
            'ensp': 'ENSEMBL_PRO_ID',
            'enst': 'ENSEMBL_TRS',
            'hgnc': 'HGNC',
        }
        self.names_uniprot_list = (
            common.swap_dict_simple(self.uniprot_list_names)
        )
    
    
    def reload(self):
        
        modname = self.__class__.__module__
        mod = __import__(modname, fromlist = [modname.split('.')[0]])
        imp.reload(mod)
        new = getattr(mod, self.__class__.__name__)
        setattr(self, '__class__', new)
    
    
    def get_table_key(
            self,
            name_type,
            target_name_type,
            ncbi_tax_id = None,
        ):
        """
        Returns a tuple unambigously identifying a mapping table.
        """
        
        ncbi_tax_id = ncbi_tax_id or self.ncbi_tax_id
        
        return MappingTableKey(
            name_type = name_type,
            target_name_type = target_name_type,
            ncbi_tax_id = ncbi_tax_id,
        )
    
    
    def which_table(
            self,
            name_type,
            target_name_type,
            load = True,
            ncbi_tax_id = None,
        ):
        """
        Returns the table which is suitable to convert an ID of
        name_type to target_name_type. If no such table have been loaded
        yet, it attempts to load from UniProt. If all attempts failed
        returns `None`.
        """
        
        tbl = None
        ncbi_tax_id = ncbi_tax_id or self.ncbi_tax_id
        
        tbl_key = self.get_table_key(
            name_type = name_type,
            target_name_type = target_name_type,
            ncbi_tax_id = ncbi_tax_id,
        )
        
        tbl_key_rev = self.get_table_key(
            target_name_type = target_name_type,
            name_type = name_type,
            ncbi_tax_id = ncbi_tax_id,
        )
        
        if tbl_key in self.tables:
            
            tbl = self.tables[tbl_key]
        
        elif tbl_name_rev in tables:
            
            self.create_reverse(tbl_key)
            tbl = self.tables[tbl_key]
            
        elif load:
            
            name_types = (name_type, target_name_type)
            name_types_rev = tuple(reversed(name_types))
            resource = None
            
            for resource_attr in ['uniprot', 'misc', 'mirbase']:
                
                resources = getattr(maps, resource_attr)
                
                if name_types in resources:
                    
                    resource = resources[name_types]
                    
                elif name_types_rev in resources:
                    
                    resource = copy.deepcopy(resources[name_types_rev])
                    resource.bi_directional = True
                
                if resource:
                    
                    self.load_mappings(
                        maplst = {name_types: resources[name_types]},
                        ncbi_tax_id = ncbi_tax_id,
                    )
                    tbl = self.which_table(
                        name_type,
                        target_name_type,
                        load = False,
                        ncbi_tax_id = ncbi_tax_id,
                    )
                    break
                
                if tbl is not None:
                    
                    break
            
            if tbl is None:
                
                if name_type in self.uniprot_list_names:
                    
                    # for uniprot/uploadlists
                    # we create here the mapping params
                    this_param = input_formats.UniprotListMapping(
                        name_type = name_type,
                        target_name_type = target_name_type,
                        ncbi_tax_id = ncbi_tax_id,
                    )
                    
                    reader = MapReader(
                        id_type_a,
                        id_type_b,
                        source_type = 'uniprotlist',
                        param = this_param,
                        ncbi_tax_id = ncbi_tax_id,
                        uniprots = None,
                        lifetime = 300,
                    )
                    
                    self.tables[tbl_key] = reader.
                
                tbl = self.which_table(
                    name_type = name_type,
                    target_name_type = target_name_type,
                    load = False,
                    ncbi_tax_id = ncbi_tax_id,
                )
            
            if tbl is None:
                
                if name_type in self.uniprot_list_names:
                    
                    self.load_uniprot_mappings([name_type])
                    
                    tbl = self.which_table(
                        name_type = name_type,
                        target_name_type = target_name_type,
                        load = False,
                        ncbi_tax_id = ncbi_tax_id,
                    )
        
        return tbl
    
    
    @staticmethod
    def reverse_mapping(mapping_table):
        
        rev_data = common.swap_dict(mapping_table.data)
        
        return MappingTable(
            data = rev_data,
            lifetime = mapping_table.lifetime,
        )
    
    
    def create_reverse(self, key):
        """
        Creates a mapping table with ``name_type`` and ``target_name_type``
        (i.e. direction of the ID translation) swapped.
        """
        
        table = self.mappings[key]
        rev_key = self.get_table_key(
            name_type = key.target_name_type,
            target_name_type = key.name_type,
            ncbi_tax_id = key.ncbi_tax_id,
        )
        
        self.tables[rev_key] = self.reverse_mapping(table)
    
    
    def map_name(
            self,
            name,
            name_type = None,
            target_name_type = None,
            ncbi_tax_id = None,
            strict = False,
            silent = True,
            nameType = None,
            targetNameType = None,
        ):
        """
        Translates one instance of one ID type to a different one.
        Returns set of the target ID type.
        
        This function should be used to convert individual IDs.
        It takes care about everything and ideally you don't need to think
        on the details.
        
        How does it work: looks up dictionaries between the original
        and target ID type, if doesn't find, attempts to load from
        the predefined inputs.
        If the original name is genesymbol, first it looks up
        among the preferred gene names from UniProt, if not
        found, it takes an attempt with the alternative gene
        names. If the gene symbol still couldn't be found, and
        strict = False, the last attempt only the first 5 chara-
        cters of the gene symbol matched. If the target name
        type is uniprot, then it converts all the ACs to primary.
        Then, for the Trembl IDs it looks up the preferred gene
        names, and find Swissprot IDs with the same preferred
        gene name.
        
        name : str
            The original name to be converted.
        name_type : str
            The type of the name.
            Available by default:
            - genesymbol (gene name)
            - entrez (Entrez Gene ID \[#\])
            - refseqp (NCBI RefSeq Protein ID \[NP\_\*|XP\_\*\])
            - ensp (Ensembl protein ID \[ENSP\*\])
            - enst (Ensembl transcript ID \[ENST\*\])
            - ensg (Ensembl genomic DNA ID \[ENSG\*\])
            - hgnc (HGNC ID \[HGNC:#\])
            - gi (GI number \[#\])
            - embl (DDBJ/EMBL/GeneBank CDS accession)
            - embl_id (DDBJ/EMBL/GeneBank accession)
            To use other IDs, you need to define the input method
            and load the table before calling :py:func:Mapper.map_name().
        target_name_type : str
            The name type to translate to, more or less the same values
            are available as for ``name_type``.
        nameType : str
            Deprecated. Synonym for ``name_type`` for backwards compatibility.
        targetNameType : str
            Deprecated. Synonym for ``target_name_type``
            for backwards compatibility.
        """
        
        name_type = name_type or nameType
        target_name_type = target_name_type or targetNameType
        
        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        
        # we support translating from more name types
        # at the same time
        if isinstance(name_type, (list, set, tuple)):
            
            return set.union(
                self.map_name(
                    name = name,
                    name_type = this_name_type,
                    target_name_type = target_name_type,
                    strict = strict,
                    silent = silent,
                    ncbi_tax_id = ncbi_tax_id,
                )
                for this_name_type in name_type
            )
        
        # translating from an ID type to the same ID type?
        if name_type == target_name_type:
            
            if target_name_type != 'uniprot':
                
                # no need for translation
                return {name}
            
            else:
                
                # we still try to search the primary UniProt
                mapped_names = {name}
            
        # actual translation comes here
        elif name_type.startswith('refseq'):
            
            # RefSeq is special
            mapped_names = self.map_refseq(
                name = name,
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
                strict = strict,
            )
            
        else:
            
            # all the other ID types
            mapped_names = self._map_name(
                name = name,
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
                strict = strict,
                name,
            )
        
        # further attempts to set it right if
        # first attempt was not successful
        if not mapped_names:
            
            # maybe it's all uppercase (e.g. human gene symbols)?
            mapped_names = self._map_name(
                name = name.upper(),
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
        
        if (
            not mapped_names and
            name_type not in {'uniprot', 'trembl', 'uniprot-sec'}
        ):
            
            # maybe it's capitalized (e.g. rodent gene symbols)?
            mapped_names = self._map_name(
                name = name.capitalize(),
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
        
        if (
            not mapped_names and
            name_type not in {'uniprot', 'trembl', 'uniprot-sec'}
        ):
            
            # maybe it's all lowercase?
            mapped_names = self._map_name(
                name = name.lower(),
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
        
        # if a gene symbol could not be translated by the default
        # conversion table, containing only the primary gene symbols
        # in next step we try the secondary (synonym) gene symbols
        if (
            not mapped_names and
            name_type == 'genesymbol'
        ):
            
            mapped_names = self._map_name(
                name = name,
                name_type = 'genesymbol-syn',
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
            
            # for gene symbols we might try one more thing,
            # sometimes the source gene symbol missing some isoform
            # information or number because it refers to the first
            # or all isoforms or subtypes; or the opposite: the
            # original resource contains a gene symbol with a number
            # appended which is not part of the official primary
            # gene symbol
            #
            # here we try to translate by adding a number `1` or
            # by matching only the first few letters;
            # obviously we can not exclude mistranslation here
            #
            # by setting `strict = True` this step is disabled
            if not strict and not mapped_names:
                
                mapped_names = self._map_name(
                    name = '%s1' % name,
                    name_type = 'genesymbol',
                    target_name_type = target_name_type,
                    ncbi_tax_id = ncbi_tax_id,
                )
                
                if not mapped_names:
                    
                    mapped_names = self._map_name(
                        name = name,
                        name_type = 'genesymbol5',
                        target_name_type = target_name_type,
                        ncbi_tax_id = ncbi_tax_id,
                    )
        
        # for miRNAs if the translation from mature miRNA name failed
        # we still try if maybe it is a hairpin name
        if not mapped_names and name_type == 'mir-mat-name':
            
            mapped_names = self._map_name(
                name = name,
                name_type = 'mir-name',
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
        
        # for UniProt IDs we do one more step:
        # try to find out the primary SwissProt ID
        if target_name_type == 'uniprot':
            
            orig = mapped_names
            mapped_names = self.primary_uniprot(mapped_names)
            mapped_names = self.trembl_swissprot(mapped_names, ncbi_tax_id)
            
            # what is this? is it necessary?
            # probably should be removed
            if len(set(orig) - set(mapped_names)) > 0:
                
                self.uniprot_mapped.append((orig, mapped_names))
            
            # why? we have no chance to have anything else here than
            # UniProt IDs
            # probably should be removed
            mapped_names = {
                u for u in mapped_names
                if self.reuniprot.match(u)
            }
        
        return mapped_names
    
    
    def map_names(
            self,
            names,
            name_type = None,
            target_name_type = None,
            ncbi_tax_id = None,
            strict = False,
            silent = True,
            nameType = None,
            targetNameType = None,
        ):
        """
        Same as ``map_name`` with multiple IDs.
        """
        
        return set.union(
            self.map_name(
                name = name,
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
                strict = strict,
                silent = silent,
                nameType = nameType,
                targetNameType = targetNameType,
            )
            for name in names
        )
    
    
    def map_refseq(
            self,
            refseq,
            name_type,
            target_name_type,
            ncbi_tax_id,
            strict = False,
        ):
        """
        ID translation adapted to the specialities of RefSeq IDs.
        """
        
        mapped_names = set()
        
        # try first as it is
        mapped_names = self._map_name(
            refseq = refseq,
            name_type = name_type,
            target_name_type = target_name_type,
            ncbi_tax_id = ncbi_tax_id,
        )
        
        # then with the number at the end removed
        # this is disabled if `strict = True`
        if not mapped_names and not strict:
            
            mapped_names = self._map_name(
                name = refseq.split('.')[0],
                name_type = name_type,
                target_name_type = target_name_type,
                ncbi_tax_id = ncbi_tax_id,
            )
        
        if not mapped_names and not strict:
            
            rstem = refseq.split('.')[0]
            
            # try some other numbers
            # this risky and is disabled if `strict = True`
            for n in xrange(49):
                
                mapped_names.update(
                    self._map_name(
                        name = '%s.%u' % (rstem, n),
                        name_type = name_type,
                        target_name_type = target_name_type,
                        ncbi_tax_id = ncbi_tax_id,
                    )
                )
        
        return mapped_names
    
    
    def _map_name(self, name, name_type, target_name_type, ncbi_tax_id):
        """
        Once we have defined the name type and the target name type,
        this function looks it up in the most suitable dictionary.
        """
        
        name_types = (name_type, target_name_type)
        nameTypRe = (target_name_type, name_type)
        tbl = self.which_table(name_type, target_name_type,
                               ncbi_tax_id = ncbi_tax_id)
        if tbl is None or name not in tbl:
            result = []
        elif name in tbl:
            result = tbl[name]
        # self.trace.append({'name': name, 'from': name_type, 'to': target_name_type,
        #    'result': result})
        
        return result
    
    
    def primary_uniprot(self, lst):
        """
        For a list of UniProt IDs returns the list of primary ids.
        """
        
        pri = []
        for u in lst:
            pr = self.map_name(u, 'uniprot-sec', 'uniprot-pri', ncbi_tax_id = 0)
            if len(pr) > 0:
                pri += pr
            else:
                pri.append(u)
        return list(set(pri))
    
    
    def trembl_swissprot(self, lst, ncbi_tax_id = None):
        """
        For a list of Trembl and Swissprot IDs, returns possibly
        only Swissprot, mapping from Trembl to gene names, and
        then back to Swissprot.
        """
        
        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        sws = []
        
        for tr in lst:
            
            sw = []
            gn = self.map_name(tr, 'trembl', 'genesymbol',
                               ncbi_tax_id = ncbi_tax_id)
            for g in gn:
                sw = self.map_name(g, 'genesymbol', 'swissprot',
                                   ncbi_tax_id = ncbi_tax_id)
            if len(sw) == 0:
                sws.append(tr)
            else:
                sws += sw
        
        sws = list(set(sws))
        return sws
    
    
    def has_mapping_table(
            self,
            name_typeA,
            name_typeB,
            ncbi_tax_id = None,
        ):
        
        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        
        if (name_typeA, name_typeB) not in self.tables[ncbi_tax_id] and \
            ((name_typeB, name_typeA) not in self.tables[ncbi_tax_id] or
                len(self.tables[ncbi_tax_id][(name_typeB, name_typeA)].mapping['form']) == 0):
            self.map_table_error(name_typeA, name_typeB, ncbi_tax_id)
            return False
        else:
            return True
    
    
    def map_table_error(self, a, b, ncbi_tax_id):
        msg = ("Missing mapping table: from `%s` to `%s` at organism `%u` "\
            "mapping needed." % (a, b, ncbi_tax_id))
        sys.stdout.write(''.join(['\tERROR: ', msg, '\n']))
        self._msg(2, msg, 'ERROR')
    
    
    def load_mappings(self, maplst=None, ncbi_tax_id = None):
        """
        mapList is a list of mappings to load;
        elements of mapList are dicts containing the
        id names, molecule type, and preferred source
        e.g. ("one": "uniprot", "two": "refseq", "typ": "protein",
        "src": "mysql", "par": "mysql_param/file_param")
        by default those are loaded from pickle files
        """

        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)

         maplst = maplst or maps.misc
        
        self._msg(1, "Loading mapping tables...")
        
        for mapName, param in iteritems(maplst):

            tables = self.tables[ncbi_tax_id]

            param = param.set_organism(ncbi_tax_id)

            self._msg(2, "Loading table %s ..." % str(mapName))
            sys.stdout.write("\t:: Loading '%s' to '%s' mapping table\n" %
                             (mapName[0], mapName[1]))

            typ = param.__class__.__name__

            if typ == 'FileMapping' and \
                    not os.path.isfile(param.input) and \
                    not hasattr(mapping_input, param.input):
                self._msg(2, "Error: no such file: %s" % param.input,
                                "ERROR")
                continue

            if typ == 'PickleMapping' and \
                    not os.path.isfile(param.pickleFile):
                self._msg(2, "Error: no such file: %s" %
                                m["par"].pickleFile, "ERROR")
                continue

            if typ == 'MysqlMapping':
                if not self.mysql:
                    self._msg(2, "Error: no mysql server known.",
                                    "ERROR")
                    continue
                else:
                    if self.mysql is None:
                        self.init_mysql()
                    param.mysql = self.mysql

            if param.ncbi_tax_id != ncbi_tax_id:
                if typ == 'FileMapping':
                    sys.stdout.write('\t:: No translation table for organism `%u`. '\
                                     'Available for `%u` in file `%s`.\n' % \
                                     (ncbi_tax_id, param.ncbi_tax_id, param.input))
                    return None

            tables[mapName] = \
                MappingTable(
                    mapName[0],
                    mapName[1],
                    param.typ,
                    typ.replace('Mapping', '').lower(),
                    param,
                    ncbi_tax_id,
                    mysql=self.mysql,
                    log=self.ownlog,
                    cache=self.cache,
                    cachedir=self.cachedir
                )

            if ('genesymbol', 'uniprot') in tables \
                and ('genesymbol-syn', 'swissprot') in tables \
                and ('genesymbol5', 'uniprot') not in tables:
                self.genesymbol5(param.ncbi_tax_id)
            self._msg(2, "Table %s loaded from %s." %
                            (str(mapName), param.__class__.__name__))
    
    
    def swissprots(self, lst):
        swprots = {}
        for u in lst:
            swprots[u] = self.map_name(u, 'uniprot', 'uniprot')
        return swprots
    
    
    def genesymbol5(self, ncbi_tax_id = None):
        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        tables = self.tables[ncbi_tax_id]
        tables[('genesymbol5', 'uniprot')] = MappingTable(
            'genesymbol5',
            'uniprot',
            'protein',
            'genesymbol5',
            None,
            ncbi_tax_id,
            None,
            log=self.ownlog)
        tbl_gs5 = tables[('genesymbol5', 'uniprot')].mapping['to']
        tbls = [
            tables[('genesymbol', 'uniprot')].mapping['to'],
            tables[('genesymbol-syn', 'swissprot')].mapping['to']
        ]
        for tbl in tbls:
            for gs, u in iteritems(tbl):
                if len(gs) >= 5:
                    gs5 = gs[:5]
                    if gs5 not in tbl_gs5:
                        tbl_gs5[gs5] = []
                    tbl_gs5[gs5] += u
        tables[('genesymbol5', 'uniprot')].mapping['to'] = tbl_gs5
    
    
    def load_uniprot_mappings(self, ac_types=None, bi=False,
                              ncbi_tax_id = None):

        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        tables = self.tables[ncbi_tax_id]
        ac_types = ac_types if ac_types is not None else self.name_types.keys()
        # creating empty MappingTable objects:
        for ac_typ in ac_types:
            tables[(ac_typ, 'uniprot')] = MappingTable(
                ac_typ,
                'uniprot',
                'protein',
                ac_typ,
                None,
                ncbi_tax_id,
                None,
                log=self.ownlog)
        # attempting to load them from Pickle
        i = 0
        for ac_typ in ac_types:
            md5ac = common.md5((ac_typ, 'uniprot', bi, ncbi_tax_id))
            cachefile = os.path.join(self.cachedir, md5ac)
            if self.cache and os.path.isfile(cachefile):
                tables[(ac_typ, 'uniprot')].mapping = \
                    pickle.load(open(cachefile, 'rb'))
                ac_types.remove(ac_typ)
                tables[(ac_typ, 'uniprot')].mid = md5ac
        # loading the remaining from the big UniProt mapping file:
        if len(ac_types) > 0:
            url = urls.urls['uniprot_idmap_ftp']['url']
            c = curl.Curl(url, silent=False, large=True)

            prg = progress.Progress(c.size, "Processing ID conversion list",
                                    99)
            for l in c.result:
                prg.step(len(l))
                l = l.decode('ascii').strip().split('\t')
                for ac_typ in ac_types:
                    if len(l) > 2 and self.name_types[ac_typ] == l[1]:
                        other = l[2].split('.')[0]
                        if l[2] not in tables[(ac_typ, 'uniprot'
                                                    )].mapping['to']:
                            tables[(
                                ac_typ, 'uniprot')].mapping['to'][other] = []
                        tables[(ac_typ, 'uniprot')].mapping['to'][other].\
                            append(l[0].split('-')[0])
                        if bi:
                            uniprot = l[0].split('-')[0]
                            if uniprot not in tables[(ac_typ, 'uniprot')].\
                                    mapping['from']:
                                tables[(ac_typ, 'uniprot')].\
                                    mapping['from'][uniprot] = []
                            tables[(ac_typ, 'uniprot')].mapping['from'][uniprot].\
                                append(other)
            prg.terminate()
            if self.cache:
                for ac_typ in ac_types:
                    md5ac = common.md5((ac_typ, bi))
                    cachefile = os.path.join(self.cachedir, md5ac)
                    pickle.dump(tables[(ac_typ, 'uniprot')].mapping,
                                open(cachefile, 'wb'))
    
    
    def save_all_mappings(self):
        
        self._msg(1, "Saving all mapping tables...")
        for ncbi_tax_id in self.tables:
            for table in self.tables[ncbi_tax_id]:
                self._msg(2, "Saving table %s ..." % table[0])
                param = mapping.pickleMapping(table)
                self.tables[m].save_mapping_pickle(param)
                self._msg(2, "Table %s has been written to %s.pickle." %
                                (m, param.pickleFile))
    
    
    def load_uniprot_mapping(self, filename, ncbi_tax_id = None):
        """
        This is a wrapper to load a ... mapping table.
        """

        ncbi_tax_id = self.get_tax_id(ncbi_tax_id)
        tables = self.tables[ncbi_tax_id]
        umap = self.read_mapping_uniprot(filename, ncbi_tax_id,
                                         self.ownlog)
        for key, value in iteritems(umap):
            tables[key] = value
    
    
    def read_mapping_uniprot_mysql(self, filename, ncbi_tax_id, log, bi=False):
        if not os.path.isfile(filename):
            self._msg(2, "No such file %s in read_mapping_uniprot()" %
                            (param, 'ERROR'))
        infile = codecs.open(filename, encoding='utf-8', mode='r')
        umap = {}
        self._msg(2, "Loading UniProt mapping table from file %s" %
                        filename)
        for line in infile:
            if len(line) == 0:
                continue
            line = line.split()
            one = line[1].lower().replace("_", "-")
            uniprot = line[0]
            other = line[2]
            mapTableName = one + "_uniprot"
            if mapTableName not in umap:
                umap[mapTableName] = mappingTable(one, "uniprot", "protein",
                                                  "uniprot", None, None,
                                                  ncbi_tax_id, log)
            if other not in umap[mapTableName].mapping["to"]:
                umap[mapTableName].mapping["to"][other] = []
            umap[mapTableName].mapping["to"][other].append(uniprot)
            if bi:
                if uniprot not in umap[mapTableName].mapping["from"]:
                    umap[mapTableName].mapping["from"][uniprot] = []
                umap[mapTableName].mapping["from"][uniprot].append(other)
        self._msg(2, "%u mapping tables from UniProt has been loaded" %
                        len(umap))
        return umap


def init():
    
    globals()['mapper'] = Mapper()


def map_name(
        name,
        name_type,
        target_name_type,
        ncbi_tax_id = None,
        strict = False,
        silent = True
    ):
    
    mapper = get_mapper()
    
    return mapper.map_name(
        name = name,
        name_type = name_type,
        target_name_type = target_name_type,
        ncbi_tax_id = ncbi_tax_id,
        strict = strict,
        silent = silent,
    )


def get_mapper():
    
    if 'mapper' not in globals():
        
        init()
    
    return globals()['mapper']


def map_names(
        names,
        name_type = None,
        target_name_type = None,
        ncbi_tax_id = None,
        strict = False,
        silent = True,
        name_type = None,
        target_name_type = None,
    ):
    
    mapper = get_mapper()
    
    return mapper.map_names(
        names = names,
        name_type = name_type,
        target_name_type = target_name_type,
        ncbi_tax_id = ncbi_tax_id,
        strict = strict,
        silent = silent,
        name_type = name_type,
        target_name_type = target_name_type,
    )
