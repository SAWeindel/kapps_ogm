from typing import Dict, Any
import logging
import json
from collections import defaultdict

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node

logger = logging.getLogger("circular_factory_ogm")


def loader_eh(node: Node) -> Dict[str, Any]:
    """
    A minimal loader function that retrieves all predicates and values for a given URI
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
    result: Dict[str, Any] = {"id": id}

    # Collect objects per predicate preserving multiplicity
    coll: Dict[str, list] = defaultdict(list)
    for _, pred, obj in triples:
        coll[pred].append(obj)

    # Flatten singletons to scalars, keep lists when multiple values exist
    for pred, objs in coll.items():
        result[pred] = objs[0] if len(objs) == 1 else objs

    # Pretty-print the result for logging
    try:
        pretty = json.dumps(result, indent=2, ensure_ascii=False)
    except Exception:
        from pprint import pformat

        pretty = pformat(result, width=120)

    logger.info("Loaded triples result:\n%s", pretty)
    return result
