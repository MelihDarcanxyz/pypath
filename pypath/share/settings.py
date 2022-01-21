#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#
#  Copyright
#  2014-2022
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  Authors: Dénes Türei (turei.denes@gmail.com)
#           Nicolàs Palacio
#           Olga Ivanova
#           Sebastian Lobentanzer
#           Ahmet Rifaioglu
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

"""
This file is part of the `pypath` python module. It provides user
settings to the remainder of PyPath modules. Settings are gathered from
`pypath/data/settings.yaml`.
"""


from future.utils import iteritems

import os, yaml
import collections

ROOT = os.path.abspath(os.getcwd())

# import settings from yaml
# we are importing from module data
settings_yaml = os.path.join(ROOT, 'pypath', 'data', 'settings.yaml')


with open(settings_yaml, 'r') as f:
    # log? ## logger is not available here, as logging parameters
    # are defined in the settings
    _defaults = yaml.load(f, Loader = yaml.FullLoader)


class Settings(object):
    """
    Class to provide settings to other modules.

    Args:
        **kwargs: key-value pairs to be included in the settings dict
    """

    def __init__(self, **kwargs):

        self.__dict__.update(kwargs)
        self.reset_all()


    def reset_all(self):
        """
        Main method of updating the settings object from data directory
        structure and the YAML file contents.
        """

        # TODO put these custom collections into YAML as well?
        in_datadir = {
            'acsn_names',
            'alzpw_ppi',
            'goose_annot_sql',
            'webpage_main',
            'nrf2ome',
            'ppoint',
            'slk3_nodes',
            'acsn',
            'arn',
            'goose_ancest_sql',
            'goose_terms_sql',
            'lmpid',
            'nci_pid',
            'old_dbptm',
            'slk3_edges',
            'slk01human',
            'deathdomain',
            'license_dir',
        }

        for k, val in _defaults.items():

            if k in in_datadir:

                val = os.path.join(ROOT, 'pypath', 'data', val)

            setattr(self, k, val)

        # runtime attributes
        # base directory
        setattr(self, 'basedir', ROOT)

        # special directories with built in default at user level
        pypath_dirs = (
            ('cachedir', 'cache'),
            ('pickle_dir', 'pickles'),
            ('secrets_dir', 'secrets'),
        )

        for _key, _dir in pypath_dirs:

            if getattr(self, _key) is None:

                setattr(
                    self,
                    _key,
                    os.path.join(
                        os.path.expanduser('~'),
                        '.pypath',
                        _dir,
                    )
                )

        in_cachedir = {
            'pubmed_cache',
            'trip_preprocessed',
            'hpmr_preprocessed',
        }

        for k in in_cachedir:

            setattr(self, k, os.path.join(self.cachedir, _defaults[k]))


        in_secrets_dir = {
            'license_secret',
        }

        for k in in_secrets_dir:

            setattr(self, k, os.path.join(self.secrets_dir, _defaults[k]))

        globals()['settings'] = self


    def setup(self, **kwargs):
        """
        This function takes a dictionary of parameters and values and sets them
        as attributes of the settings object.

        Args:
        **kwargs: key-value pairs to set in the `settings` object

        Returns:
        None
        """

        for param, value in iteritems(kwargs):

            setattr(self, param, value)


    def get(self, param, value = None):
        """
        Retrieves the current value of a parameter.

        :param str param:
            The key for the parameter.
        :param object,NoneType value:
            If this value is not None it will be returned instead of the settings
            value. It is useful if the parameter provided at the class or method
            level should override the one in settings.
        """

        if value is not None:

            return value

        if hasattr(self, param):

            return getattr(self, param)



    def get_default(self, param):
        """
        Returns the value of the parameter in the defaults object if it
        exists, otherwise returns None.

        Args:
        param: keyword to look for in `defaults`

        Returns:
        The value of the parameter or None.
        """

        if hasattr(defaults, param):

            return getattr(defaults, param)


    def reset(self, param):
        """
        Reset the parameters to their default values.

        Args:
        param: the name of the parameter to be set

        Returns:
        None
        """

        self.setup(**{param: self.get_default(param)})


settings = Settings()

def get(param, value = None):
    """
    Wrapper of Settings.get().
    """
    return settings.get(param, value)


# deprecated

_defaults_old = {
    # name of the module
    'module_name': 'pypath',
    # The absolute root directory.
    # This should not be necessary, why is it here?
    'path_root': '/',
    # The basedir for every files and directories in the followings.
    'basedir': os.getcwd(),

    'progressbars': False,
    # verbosity for messages printed to console
    'console_verbosity': -1,
    # verbosity for messages written to log
    'log_verbosity': 0,
    # log flush time interval in seconds
    'log_flush_interval': 2,
    # check for expired mapping tables and delete them
    # (period in seconds)
    'mapper_cleanup_interval': 60,
    'mapper_translate_deleted_uniprot': False,
    'mapper_keep_invalid_uniprot': False,
    'mapper_trembl_swissprot_by_genesymbol': True,
    # If None will be the same as ``basedir``.
    'data_basedir': None,
    'acsn_names': 'acsn_names.gmt',
    'alzpw_ppi': 'alzpw-ppi.csv',
    'goose_annot_sql': 'goose_annotations.sql',
    'webpage_main': 'main.html',
    'nrf2ome': 'nrf2ome.csv',
    'ppoint': 'phosphopoint.csv',
    'slk3_nodes': 'signalink3_nodes.tsv',
    'acsn': 'acsn_ppi.txt',
    'arn': 'arn_curated.csv',
    'goose_ancest_sql': 'goose_ancestors.sql',
    'goose_terms_sql': 'goose_terms.sql',
    'lmpid': 'LMPID_DATA_pubmed_ref.xml',
    'nci_pid': 'nci-pid-strict.csv',
    'old_dbptm': 'old_dbptm.tab',
    'slk3_edges': 'signalink3_edges.tsv',
    'slk01human': 'slk01human.csv',
    'cachedir': None,
    # directory in datadir with licenses
    'license_dir': 'licenses',
    # password file for within company license-free redistribution
    'secrets_dir': None,
    # web contents root directory path (for server)
    'www_root': 'www',
    'license_secret': 'license_secret',
    'server_default_license': 'academic',
    'server_annotations_full_download': False,
    'pubmed_cache': 'pubmed.pickle',
    'mapping_use_cache': True,
    'use_intermediate_cache': True,
    'default_organism': 9606,
    'default_name_types': {
        'protein': 'uniprot',
        'mirna': 'mirbase',
        'drug': 'pubchem',
        'lncrna': 'lncrna-genesymbol',
        'small_molecule': 'pubchem',
    },
    'default_label_types': {
        'protein': 'genesymbol',
        'mirna': 'mir-mat-name',
        'lncrna': 'lncrna-genesymbol',
        'small_molecule': 'rxnorm',
        'drug': 'rxnorm',
    },
    'small_molecule_entity_types': {
        'small_molecule',
        'drug',
        'metabolite',
        'lipid',
        'compound',
    },
    'uniprot_uploadlists_chunk_size': 10000,
    'trip_preprocessed': 'trip_preprocessed.pickle',
    'deathdomain': 'deathdomain.tsv',
    'hpmr_preprocessed': 'hpmr_preprocessed.pickle',
    'network_expand_complexes': False,
    'network_allow_loops': False,
    'network_keep_original_names': True,
    'network_pickle_cache': True,
    'go_pickle_cache': True,
    'go_pickle_cache_fname': 'goa__%u.pickle',
    'network_extra_directions': {
        'Wang',
        'KEGG',
        'STRING',
        'ACSN',
        'PhosphoSite',
        'PhosphoPoint',
        'CancerCellMap',
        'PhosphoSite_dir',
        'PhosphoSite_noref',
        'PhosphoNetworks',
        'MIMP',
        'HPRD-phos',
    },
    'keep_noref': False,
    'msigdb_email': 'omnipathdb@gmail.com',

    # the annotation classes should infer complex annotations
    # from protein annotations
    'annot_infer_complexes': True,
    # the resource name for annotation categories
    # combined from multiple original resources
    'annot_composite_database_name': 'OmniPath',

    # load small, specific categories from CellPhoneDB
    # in the intercell database
    'intercell_cellphonedb_categories': True,
    # same for Baccin2019 and some others
    'intercell_baccin_categories': True,
    'intercell_hpmr_categories': True,
    'intercell_surfaceome_categories': True,
    'intercell_gpcrdb_categories': True,
    'intercell_icellnet_categories': True,

    # parameters for pypath.omnipath
    'timestamp_format': '%Y%m%d',

    # tfregulons levels
    'tfregulons_levels': {'A', 'B', 'C', 'D'},

    # datasets
    'datasets': [
       'omnipath',
       'curated',
       'complex',
       'annotations',
       'intercell',
       'tf_target',
       'tf_mirna',
       'mirna_mrna',
       'lncrna_mrna',
       'enz_sub',
    ],

    'omnipath_mod': 'network',
    'curated_mod': 'network',
    'complex_mod': 'complex',
    'annotations_mod': 'annot',
    'intercell_mod': 'intercell',
    'enz_sub_mod': 'enz_sub',
    'tf_target_mod': 'network',
    'tf_mirna_mod': 'network',
    'mirna_mrna_mod': 'network',
    'lncrna_mrna_mod': 'network',
    'small_molecule_mod': 'network',

    'omnipath_args': {
        'use_omnipath': True,
        'kinase_substrate_extra': True,
        'ligand_receptor_extra': True,
        'pathway_extra': True,
        'allow_loops': True,
    },

    'tf_target_args': {
        'method': 'load_transcription',
        'dorothea_levels': {'A', 'B', 'C', 'D'},
        'allow_loops': True,
    },

    # only for pypath.omnipath.app and pypath.core.network
    'dorothea_expand_levels': False,

    'dependencies': {
        'intercell': ('annotations',),
        'annotations': ('complex',),
    },

    'omnipath_pickle': 'network_omnipath.pickle',
    'curated_pickle': 'network_curated.pickle',
    'complex_pickle': 'complexes.pickle',
    'annotations_pickle': 'annotations.pickle',
    'intercell_pickle': 'intercell.pickle',
    'enz_sub_pickle': 'enz_sub_%u.pickle',
    'tf_target_pickle': 'tftarget.pickle',
    'tf_mirna_pickle': 'tfmirna.pickle',
    'mirna_mrna_pickle': 'mirna_mrna.pickle',
    'lncrna_mrna_pickle': 'lncrna_mrna.pickle',
    'small_molecule_pickle': 'small_molecule.pickle',

    'pickle_dir': None,

    # directory for exported tables
    'tables_dir': 'omnipath_tables',

    # directory for figures
    'figures_dir': 'omnipath_figures',

    # directory for LaTeX
    'latex_dir': 'omnipath_latex',

    # include a timestamp in directory names
    'timestamp_dirs': True,

    # maximum lenght of the strings in UniProt info printed tables
    'uniprot_info_maxlen': 500,
    # at downloading UniProt datasheets the default very long timeouts,
    # that we use in the curl module, especially because many of our downloads
    # are huge, are too long and better to start the next attempt sooner if
    # the first fails to respond. Similarly for trying to download datasets
    # via curl.py.
    'uniprot_datasheet_connect_timeout': 10,
    'uniprot_datasheet_timeout': 20,
    'genecards_datasheet_connect_timeout': 10,
    'genecards_datasheet_timeout': 20,
    'curl_connect_timeout': 10,
    'curl_timeout': 20,

    # certain servers (e.g. Cloudflare) banned curl as an user agent;
    # we use the header below to override the default value in those cases:
    'user_agent': 'User-Agent: Mozilla/5.0 '
        '(X11; U; Linux i686; en-US; rv:54.0) Gecko/20110304 Firefox/54.0',

    # Ensembl homology high confidence and types
    'homology_ensembl_hc': True,
    'homology_ensembl_types': 'one2one',
    'homology_ensembl': True,
    'homology_homologene': True,

}
