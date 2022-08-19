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
#           Sebastian Lobentanzer
#           Erva Ulusoy
#           Olga Ivanova
#           Ahmet Rifaioglu
#           Tennur Kılıç
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

import csv
import collections
import base64

import pypath.resources.urls as urls
import pypath.share.curl as curl
import pypath.share.session as session
import pypath.share.settings as settings

_logger = session.Logger(name = 'drugbank')
_log = _logger._log


def _drugbank_download(user: str, passwd: str, *args, **kwargs):

    defaults = {
        'large': True,
        'silent': False,
        'compr': 'zip',
    }

    defaults.update(kwargs)

    auth_str = base64.b64encode(f"{user}:{passwd}".encode())

    defaults['req_headers'] = [
        f'Authorization: Basic {auth.decode()}',
        settings.get('user_agent'),
    ]

    return curl.Curl(*args, **defaults)


def drugbank_raw_interactions(
        user: str,
        passwd: str,
        pharma_active: bool = False,
    ) -> list[tuple] :
    """
    Retrieves protein identifiers from Drugbank.

    Args:
        user:
            E-mail address with registered DrugBank account.
        passwd:
            Password for the DrugBank account.
        pharma_active:
            Only pharmacologically active relations.

    Returns:
        List of drug-protein relations.
    """

    csv_name = 'pharmacologically_active.csv' if pharma_active else 'all.csv'

    fields = (
        'drugbank_id',
        'uniprot_id',
        'relation',
    )

    DrugbankRawInteraction = collections.namedtuple(
        'DrugbankRawInteraction',
        fields,
        defaults = (None,) * len(fields),
    )

    result = []

    for rel in ('carrier', 'enzyme', 'target', 'transporter'):

        url = urls.urls['drugbank'][f'drug_{rel}_identifiers']

        c = _drugbank_download(
            url = url,
            user = user,
            passwd = passwd,
            files_needed = (csv_name,),
        )

        _ = next(c.result[csv_name])

        for l in c.result[csv_name]:

            drugs, uniprot = l.strip().split(',')

            result.extend(
                DrugbankRawInteraction(
                    drugbank_id = drug,
                    uniprot_id = uniprot,
                    relation = rel,
                )
                for drug in drugs
            )

    return result


def drugbank_drugs(user: str, passwd: str) -> list[tuple] :
    """
    Retrieves drug identifiers from Drugbank.

    Each drug is annotated by its various database cross-references.

    Args:
        user:
            E-mail address with registered DrugBank account.
        passwd:
            Password for the DrugBank account.

    Returns:
        List of named tuples, each field corresponding to various identifiers.
    """

    fields = (
        'drugbank',
        'name',
        'type',
        'groups',
        'cas',
        'inchikey',
        'inchi',
        'smiles',
        'formula',
        'kegg_compound',
        'kegg_drug',
        'pubchem_cid',
        'pubchem_sid',
        'chebi',
        'chembl',
        'pharmgkb',
        'het',
    )

    raw = {}

    for table in ('drug', 'structure'):

        csv = f'{table} links.csv'

        c = _drugbank_download(
            url = urls.urls['drugbank'][f'all_{table}s'],
            user = user,
            passwd = passwd,
            files_needed = (csv,),
        )

        raw[table] = dict(
            (rec['DrugBank ID'], rec)
            for rec in csv.DictReader(c.result[csv], delimiter = ',')
        )

    DrugbankDrug = collections.namedtuple(
        'DrugbankDrug',
        fields,
        defaults = (None,) * len(fields),
    )

    result = []

    for dbid, struct in raw['structure'].items():

        drug = raw['drug'].get(dbid, {})

        result.append(
            DrugbankDrug(
                drugbank = dbid,
                name = struct['Name'],
                type = drug.get('Drug Type', None),
                groups = struct['Drug Groups'],
                cas = struct['CAS Number'],
                inchikey = struct['InChIKey'],
                inchi = struct['InChI'],
                smiles = struct['SMILES'],
                formula = struct['Formula'],
                kegg_compound = struct['KEGG Compound ID'],
                kegg_drug = struct['KEGG Drug ID'],
                pubchem_cid = struct['PubChem Compound ID'],
                pubchem_sid = struct['PubChem Substance ID'],
                chebi = struct['ChEBI ID'],
                chembl = struct['ChEMBL ID'],
                pharmgkb = drug.get('PharmGKB ID', None)
                het = drug.get('HET ID', None),
            )
        )

    return result
