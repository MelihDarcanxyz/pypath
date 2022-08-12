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

from typing import List

import os
import csv
import collections
import base64

import pypath.resources.urls as urls
import pypath.share.curl as curl
import pypath.share.session as session
import pypath.share.settings as settings

_logger = session.Logger(name = 'drugbank')
_log = _logger._log

def add_prot_id(
        user: str,
        passwd: str,
        pharma_active: bool = False,
    ) -> List[tuple] :
    """
    Retrieves protein identifiers from Drugbank.

    Args:
        user (str): E-mail address for login to DrugBank.
        passwd (str): Password for login to DrugBank.
        pharma_active (bool): Wheter to include pharmacologically active identifiers.

    Returns:
        namedtuple.
    """

    credentials = {'user': user, 'passwd': passwd}

    auth_str = base64.b64encode(
        ('%s:%s' % (credentials['user'], credentials['passwd'])).encode()
    ).decode()

    decoded = 'Basic %s' % auth_str

    req_hdrs = ['Authorization: %s' % decoded]
    req_hdrs.extend([settings.get('user_agent')])

    fields = ('DrugBank_ID','Target_UniProt_ID','Transporter_UniProt_ID','Enzym_UniProt_ID','Carrier_UniProt_ID')

    ProteinIdentifiers = collections.namedtuple('ProteinIndetifiers', fields,defaults = ("",) * len(fields))

    url = urls.urls['drugbank']['drug_enzym_identifiers']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False,
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".csv.zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".csv.zip")
    enzym = list(csv.DictReader(zipfile.result["all.csv"], delimiter = ','))

    if pharma_active:

        active = list(csv.DictReader(zipfile.result["pharmacologically_active.csv"], delimiter = ','))

        for rec in active:

            enzym.append(rec)

    result = []

    result.append(
        ProteinIdentifiers(
            DrugBank_ID = "",
            )
        )

    for enzym_attr in enzym:

        DrugBank_IDs = [i for i in enzym_attr['Drug IDs'].replace(" ","").split(';')]

        for id in DrugBank_IDs:

            index = 0
            flag = 0

            for res_attr in result:

                if id == res_attr.DrugBank_ID:

                    flag = 1

                    if res_attr.Enzym_UniProt_ID == "":

                        result[index] = result[index]._replace(
                        Enzym_UniProt_ID = enzym_attr['UniProt ID'],)

                    else:

                        result[index] = result[index]._replace(
                        Enzym_UniProt_ID = result[index].Enzym_UniProt_ID + ";" + enzym_attr['UniProt ID'],)

                    break

                index += 1

            if flag == 0:

                result.append(
                    ProteinIdentifiers(
                        DrugBank_ID = id,
                        Enzym_UniProt_ID = enzym_attr['UniProt ID'],
                        )
                    )

    del result[0]

    url = urls.urls['drugbank']['drug_carrier_identifiers']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False,
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".csv.zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".csv.zip")
    carrier = list(csv.DictReader(zipfile.result["all.csv"], delimiter = ','))

    if pharma_active:

        active = list(csv.DictReader(zipfile.result["pharmacologically_active.csv"], delimiter = ','))

        for rec in active:

            carrier.append(rec)

    for carrier_attr in carrier:

        DrugBank_IDs = [i for i in carrier_attr['Drug IDs'].replace(" ","").split(';')]

        for id in DrugBank_IDs:

            index = 0
            flag = 0

            for res_attr in result:

                if id == res_attr.DrugBank_ID:

                    flag = 1

                    if res_attr.Carrier_UniProt_ID == "":

                        result[index] = result[index]._replace(
                        Carrier_UniProt_ID = carrier_attr['UniProt ID'],)

                    else:

                        result[index] = result[index]._replace(
                        Carrier_UniProt_ID = result[index].Carrier_UniProt_ID + ";" + carrier_attr['UniProt ID'],)

                    break

                index += 1

            if flag == 0:

                result.append(
                    ProteinIdentifiers(
                        DrugBank_ID = id,
                        Carrier_UniProt_ID = carrier_attr['UniProt ID'],
                        )
                    )


    url = urls.urls['drugbank']['drug_transporter_identifiers']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False,
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".csv.zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".csv.zip")
    transporter = list(csv.DictReader(zipfile.result["all.csv"], delimiter = ','))

    if pharma_active:

        active = list(csv.DictReader(zipfile.result["pharmacologically_active.csv"], delimiter = ','))

        for rec in active:

            transporter.append(rec)

    for transporter_attr in transporter:

        DrugBank_IDs = [i for i in transporter_attr['Drug IDs'].replace(" ","").split(';')]

        for id in DrugBank_IDs:

            index = 0
            flag = 0

            for res_attr in result:

                if id == res_attr.DrugBank_ID:

                    flag = 1

                    if res_attr.Transporter_UniProt_ID == "":

                        result[index] = result[index]._replace(
                        Transporter_UniProt_ID = transporter_attr['UniProt ID'],)

                    else:

                        result[index] = result[index]._replace(
                        Transporter_UniProt_ID = result[index].Transporter_UniProt_ID + ";" + transporter_attr['UniProt ID'],)

                    break

                index += 1

            if flag == 0:

                result.append(
                    ProteinIdentifiers(
                        DrugBank_ID = id,
                        Transporter_UniProt_ID = transporter_attr['UniProt ID'],
                        )
                    )

    url = urls.urls['drugbank']['drug_target_identifiers']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False,
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".csv.zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".csv.zip")
    target = list(csv.DictReader(zipfile.result["all.csv"], delimiter = ','))

    if pharma_active:

        active = list(csv.DictReader(zipfile.result["pharmacologically_active.csv"], delimiter = ','))

        for rec in active:

            target.append(rec)

    for target_attr in target:

        DrugBank_IDs = [i for i in target_attr['Drug IDs'].replace(" ","").split(';')]

        for id in DrugBank_IDs:

            index = 0
            flag = 0

            for res_attr in result:

                if id == res_attr.DrugBank_ID:

                    flag = 1

                    if res_attr.Target_UniProt_ID == "":

                        result[index] = result[index]._replace(
                        Target_UniProt_ID = target_attr['UniProt ID'],)

                    else:

                        result[index] = result[index]._replace(
                        Target_UniProt_ID = result[index].Target_UniProt_ID + ";" + target_attr['UniProt ID'],)

                    break

                index += 1

            if flag == 0:

                result.append(
                    ProteinIdentifiers(
                        DrugBank_ID = id,
                        Target_UniProt_ID = target_attr['UniProt ID'],
                        )
                    )

    return result

def drug_bank(
        user: str,
        passwd: str,
        addprotid: bool = True,
        pharma_active: bool = False,
    ) -> List[tuple] :
    """
    Retrieves structures, external links and protein identifiers from Drugbank.

    Args:
        user (str): E-mail address for login to DrugBank.
        passwd (str): Password for login to DrugBank.
        addprotid (bool): Wheter to include protein identifiers from DrugBank.
        pharma_active (bool): Wheter to include pharmacologically active identifiers.

    Returns:
        namedtuple.
    """

    fields = ('DrugBank_ID','Name','CAS_Number','Drug_Groups','InChIKey','InChI','SMILES','Formula',
                'KEGG_Compound_ID','KEGG_Drug_ID','PubChem_Compound_ID','PubChem_Substance_ID','ChEBI_ID',
                'ChEMBL_ID','Drug_Type','PharmGKB_ID','HET_ID','Target_UniProt_ID','Transporter_UniProt_ID',
                'Enzym_UniProt_ID','Carrier_UniProt_ID')

    credentials = {'user': user, 'passwd': passwd}

    auth_str = base64.b64encode(
        ('%s:%s' % (credentials['user'], credentials['passwd'])).encode()
    ).decode()

    decoded = 'Basic %s' % auth_str

    req_hdrs = ['Authorization: %s' % decoded]
    req_hdrs.extend([settings.get('user_agent')])

    url = urls.urls['drugbank']['all_structures']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".zip")
    structure_links = list(csv.DictReader(zipfile.result["structure links.csv"], delimiter = ','))

    url = urls.urls['drugbank']['all_drug']
    c = curl.Curl(
        url,
        large = True,
        silent = False,
        req_headers = req_hdrs,
        cache = False
    )

    os.rename(c.fileobj.name, c.fileobj.name + ".zip")
    zipfile = curl.FileOpener(c.fileobj.name + ".zip")
    drug_links = list(csv.DictReader(zipfile.result["drug links.csv"], delimiter = ','))

    if addprotid:

        Combine = collections.namedtuple('Combine', fields,defaults = ("",) * len(fields))

    else:
        Combine = collections.namedtuple('Combine', fields[:17],defaults = ("",) * len(fields[:17]))

    result = []

    for struct_attr in structure_links:

        for drug_attr in drug_links:

            if struct_attr['DrugBank ID'] == drug_attr['DrugBank ID']:

                result.append(
                    Combine(
                        DrugBank_ID = struct_attr['DrugBank ID'],
                        Name = struct_attr['Name'],
                        CAS_Number = struct_attr['CAS Number'],
                        Drug_Groups = struct_attr['Drug Groups'],
                        InChIKey = struct_attr['InChIKey'],
                        InChI = struct_attr['InChI'],
                        SMILES = struct_attr['SMILES'],
                        Formula = struct_attr['Formula'],
                        KEGG_Compound_ID = struct_attr['KEGG Compound ID'],
                        KEGG_Drug_ID = struct_attr['KEGG Drug ID'],
                        PubChem_Compound_ID = struct_attr['PubChem Compound ID'],
                        PubChem_Substance_ID = struct_attr['PubChem Substance ID'],
                        ChEBI_ID = struct_attr['ChEBI ID'],
                        ChEMBL_ID = struct_attr['ChEMBL ID'],
                        Drug_Type = drug_attr['Drug Type'],
                        PharmGKB_ID = drug_attr['PharmGKB ID'],
                        HET_ID = drug_attr['HET ID'],
                    )
                )

    if addprotid:

        identifiers_list = add_prot_id(user, passwd, pharma_active)
        index = 0

        for res_attr in result:

            for iden_attr in identifiers_list:

                if res_attr.DrugBank_ID == iden_attr.DrugBank_ID:

                    result[index] = result[index]._replace(
                        Target_UniProt_ID = iden_attr.Target_UniProt_ID,
                        Transporter_UniProt_ID = iden_attr.Transporter_UniProt_ID,
                        Enzym_UniProt_ID = iden_attr.Enzym_UniProt_ID,
                        Carrier_UniProt_ID = iden_attr.Carrier_UniProt_ID,
                    )

                    break

            index += 1


    return result
