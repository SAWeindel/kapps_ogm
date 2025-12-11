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


def resolve_bnode(
    subj: IRI, pred: IRI, db: GraphDB, blacklist: set, ogm: OGM
) -> Dict[IRI, Any]:
    """
    Helper function to handle blank nodes (BNodes) if needed.
    expands the blanknode and returns its properties as a dict.
    """
    query = SPARQLQuery(include_implicit=False)
    where_clauses = [
        f"{subj.n3()} {pred.n3()} ?bnode .",
        "?bnode ?attribute ?field .",
    ]
    query.add_select_block(["?attribute", "?field"], where_clauses=where_clauses)
    query_result = db.query(query, convert_bindings=True)
    bnode_data: Dict[IRI, list[Any]] = defaultdict(list)
    for result in query_result["results"]["bindings"]:
        attribute = result["attribute"]
        field = result["field"]

        if attribute in blacklist:
            continue

        # determine value according to result type
        if isinstance(field, IRI) and db.owl_is_named_individual(iri=field):
            value = ogm.create_node(id=field)
        else:
            value = field

        bnode_data[attribute].append(value)

    return bnode_data


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
    blacklist = ogm.expansion_blacklist

    # Fetch triples for the subject
    triples = db.triples_get(sub=id)

    # Start result with stringified id
    result: Dict[IRI, list[Any]] = defaultdict(list)

    result["id"] = id

    # Collect objects per predicate preserving multiplicity
    for _, predicate, object in triples:

        logger.debug("Processing object for %s -> %s", predicate, object)
        if isinstance(object, BNode):
            # expand the blank node into its properties dict
            object = resolve_bnode(id, predicate, db, blacklist, ogm)
        elif isinstance(object, IRI):
            # Create a Node for the referenced IRI and load it so it becomes persisted
            object = ogm.create_node(id=object)

        result[predicate].append(object)

    # Pretty-print the result for logging
    try:
        pretty = json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            cls=OGMEncoder,
        )

    except Exception:
        from pprint import pformat

        pretty = pformat(result, width=120)
    logger.info("Loaded triples result:\n%s", pretty)

    return result
