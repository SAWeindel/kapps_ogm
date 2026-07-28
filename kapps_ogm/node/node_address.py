"""Address reconciliation between a fetched node and the node about to be written."""

from __future__ import annotations

from typing import TYPE_CHECKING

from graph_db_interface import IRI

if TYPE_CHECKING:
    from .core import Node


def reconcile_anonymous_addresses(*, old: "Node", new: "Node") -> None:
    """
    Copy stable anonymous-node addresses from a fetched node onto the node about to be written.

    An anonymous node's address is deliberately absent from the pydantic projection, so a caller
    who fetches, calls ``model_dump()``, edits a value and commits the plain dict has no address
    in their payload. Without this step every commit would mint a fresh address, delete the old
    node and strand every triple the ClassSpec does not declare — the failure this whole mechanism
    exists to prevent. The address is therefore recovered from the store side instead.

    Entries are aligned positionally, which is why ``OGM._fetch_complex_property`` returns its
    groups in a deterministic order: both the caller's earlier fetch and the fetch inside
    ``commit`` then see the same sequence. A value with no counterpart on the old side is a
    genuinely new node and is left unaddressed, so that ``OGM._assign_id`` mints for it.

    An old address that is still a blank node is **not** copied. The node has not been skolemised
    yet, so leaving the new one unaddressed relocates it to a Skolem IRI on this write — a
    one-time migration, after which its address is stable.

    Args:
        old: The node as fetched from the store, carrying the authoritative addresses.
        new: The node about to be written. Mutated in place.
    """
    from .core import Node

    if not old.data or not new.data:
        return

    for property_iri, new_values in new.data.items():
        old_values = old.data.get(property_iri)
        if not old_values:
            continue

        for index, new_value in enumerate(new_values):
            if index >= len(old_values):
                # A genuinely new value: nothing to adopt, so it gets minted on write.
                break

            old_value = old_values[index]
            if not isinstance(new_value, Node) or not isinstance(old_value, Node):
                continue

            if new_value.id is None and isinstance(old_value.id, IRI):
                new_value.id = old_value.id

            reconcile_anonymous_addresses(old=old_value, new=new_value)
