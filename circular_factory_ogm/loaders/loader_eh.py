from typing import Dict, Any
import logging
import json
from collections import defaultdict
from rdflib import BNode
from graph_db_interface import IRI, SPARQLQuery

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node

logger = logging.getLogger("circular_factory_ogm")


def resolve_bnode(subj: IRI, pred: IRI, db: GraphDB, blacklist: set, ogm: Any) -> Dict[str, Any]:
    """
    Helper function to handle blank nodes (BNodes) if needed.
    expands the blanknode and returns its properties as a dict.
    """
    query = SPARQLQuery(include_implicit=False)
    where_clauses = [f"<{str(subj)}> <{str(pred)}> ?bnode .", "?bnode ?p ?o ."]
    query.add_select_block(["?p", "?o"], where_clauses=where_clauses)
    query_result = db.query(query.to_string())
    bnode_data: Dict[str, Any] = {}
    for result in query_result["results"]["bindings"]:
        predicate = IRI(result["p"]["value"])
        obj_val = result["o"]
        object_type = obj_val["type"]

        if predicate in blacklist:
            continue

        key = str(predicate)
        # determine value according to SPARQL result type
        if object_type == "literal":
            value: Any = obj_val["value"]
        elif object_type == "uri":
            object = IRI(obj_val["value"])
            if db.owl_is_named_individual(iri=object):
                value = ogm.create_node(id=object)
            else:
                value = IRI(obj_val["value"])
        
        else:
            # fallback: keep raw value
            value = obj_val.get("value")

        # when key already present, ensure we preserve multiplicity
        if key in bnode_data:
            existing = bnode_data[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                bnode_data[key] = [existing, value]
        else:
            bnode_data[key] = value

    return bnode_data


def loader_eh(node: Node) -> Dict[str, Any]:
    """
    Minimal loader that loads triples and values for a given URI
    from a GraphDB triplestore and returns them as a dictionary.

    This version preserves multiple objects for the same predicate by collecting
    them into lists. Singletons are left as scalars for convenience.
    """
    id = node.id
    ogm = node.ogm
    db = ogm.db
    blacklist = ogm.expansion_blacklist

    # Fetch triples for the subject
    triples = db.triples_get(sub=id)

    # Start result with stringified id
    result: Dict[str, Any] = {}

    # Collect objects per predicate preserving multiplicity
    coll: Dict[str, list] = defaultdict(list)
    for _, pred, obj in triples:
        coll[pred].append(obj)

    # Flatten singletons to scalars, keep lists when multiple values exist
    for pred, objs in coll.items():
        if pred in blacklist:
            logger.debug(
                "Skipping expansion of blacklisted predicate %s for node %s", pred, id
            )
            continue

        # Transform each object in-place so changes are reflected in the returned result
        for idx, obj in enumerate(objs):
            logger.debug("Processing object for %s -> %s", pred, obj)
            if isinstance(obj, BNode):
                # expand the blank node into its properties dict
                try:
                    bnode_props = resolve_bnode(id, pred, db, blacklist, ogm)
                    transformed = bnode_props
                except Exception:
                    logger.exception("Failed to resolve bnode for %s %s", id, pred)
                    transformed = obj
            elif isinstance(obj, IRI) and db.owl_is_named_individual(iri=obj):
                # Create a Node for the referenced IRI and load it so it becomes persisted

                transformed = ogm.create_node(id=obj)
            else:
                # literal or plain IRI (not a named individual) — keep as-is
                transformed = obj

            # replace in the list so result includes the transformed object
            objs[idx] = transformed

        # store list (keep list even for singletons to preserve multiplicity)
        result[pred] = objs

    # Pretty-print the result for logging
    try:
        pretty = json.dumps(result, indent=2, ensure_ascii=False)
    except Exception:
        from pprint import pformat

        pretty = pformat(result, width=120)

    logger.info("Loaded triples result:\n%s", pretty)
    return result
