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

import pypath.dataio as dataio
import pypath.intera as intera
import pypath.resource as resource


class AbstractComplexResource(resource.AbstractResource):
    """
    A resource which provides information about molecular complexes.
    """
    
    
    def __init__(
            self,
            name,
            mapper = None,
            ncbi_tax_id = 9606,
            input_method = None,
            input_args = None,
            **kwargs,
        ):
        """
        name : str
            Custom name for the resource.
        input_method : callable
            Method providing the input data.
        process_method : callable
            Method processing the data and yielding ``intera.Complex``
            instances.
        """
        
        self.complexes = {}
        
        resource.AbstractResource.__init__(
            self,
            name = name,
            mapper = mapper,
            ncbi_tax_id = ncbi_tax_id,
            input_method = input_method,
            input_args = input_args,
        )
        
        self.load()
    
    
    def load(self):
        
        resource.AbstractResource.load(self)
        self.update_index()
    
    
    def __iter__(self):
        
        for cplex in self.complexes.values():
            
            yield cplex
    
    
    def update_index(self):
        
        self.proteins = collections.defaultdict(set)
        self.resources = collections.defaultdict(set)
        
        for cplex in self:
            
            for protein in cplex:
                
                self.proteins[protein].add(cplex)
            
            for db in cplex.sources:
                
                self.resources.add(cplex)