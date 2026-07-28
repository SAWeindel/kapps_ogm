"""Exception types for the kapps_ogm package."""

from __future__ import annotations


class AnonymousNodeFetchError(ValueError):
    """Raised when OGM.fetch is called on a Skolem IRI.

    Skolem IRIs identify anonymous nodes that have no rdf:type and can only be reached
    through their parent node. Attempting to fetch them directly would bypass the structural
    context required to interpret them correctly.
    """

    pass


class UnresolvableNodeAddressError(ValueError):
    """Raised on the write path when the RDF address of an anonymous node cannot be resolved.

    This exception exists so that an unresolvable target can never silently become a freshly
    minted node, which would orphan every triple the ClassSpec does not declare. It protects
    referential integrity during serialization and commit operations.
    """

    pass
