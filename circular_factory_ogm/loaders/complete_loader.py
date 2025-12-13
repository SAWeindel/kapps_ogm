from typing import Dict, Any
import logging
import json
from collections import defaultdict
from rdflib import BNode
from graph_db_interface import IRI, SPARQLQuery

from graph_db_interface import GraphDB, IRI
from graph_db_interface.utils.pretty_print import shorten_block

from circular_factory_ogm.node import Node
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder

logger = logging.getLogger("cf_loader_eh")

def loader_eh(node: Node) -> Dict[IRI, Any]:
    """
    Minimal loader that loads triples and values for a given URI
    from a GraphDB triplestore and returns them as a dictionary.

    This version preserves multiple objects for the same predicate by collecting
    them into lists.
    """
    id = node.id
    ogm = node.ogm
    db = ogm.db

    

    return result