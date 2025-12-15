from typing import Dict, Any
import logging
import json
from collections import defaultdict
from rdflib import BNode
from graph_db_interface import IRI, SPARQLQuery

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder

logger = logging.getLogger("cf_loader_eh")


def resolve_bnode(
    subj: IRI, pred: IRI, db: GraphDB, expansion_handler: Dict[IRI, Any], ogm: OGM
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

        # Check if there's a custom handler for this attribute
        if attribute in expansion_handler:
            handler = expansion_handler[attribute]
            value = handler(field, ogm)
        # determine value according to result type
        elif isinstance(field, IRI) and db.owl_is_named_individual(iri=field):
            value = ogm.create_node(id=field)
        else:
            value = field

        bnode_data[attribute].append(value)

    return bnode_data


def resolve_rdf_type(node: Node, db: GraphDB, ogm: OGM) -> Any:
    subj = node.id
    result = db.triples_get(
        sub=subj, pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    )
    types = [obj for _, _, obj in result]
    for t in types:
        logger.debug("Found rdf:type %s for subject %s", t, subj)


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
    # expansion_handler = ogm.expansion_handler
    resolve_rdf_type(id, db, ogm)

    # Fetch triples for the subject
    triples = db.triples_get(sub=id)

    # Start result with stringified id
    result: Dict[IRI, list[Any]] = defaultdict(list)

    result["id"] = id

    # Collect objects per predicate preserving multiplicity
    for _, pred, obj in triples:

        logger.debug("Processing object for %s -> %s", pred, obj)

        # Check if there's a custom handler for this predicate
        if pred in expansion_handler:
            handler = expansion_handler[pred]
            obj = handler(obj, ogm)
        elif isinstance(obj, BNode):
            # expand the blank node into its properties dict
            obj = resolve_bnode(
                id, pred, db, expansion_handler=expansion_handler, ogm=ogm
            )
        elif isinstance(obj, IRI):
            # Create a Node for the referenced IRI and load it so it becomes persisted
            obj = ogm.create_node(id=obj)

        result[pred].append(obj)

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
