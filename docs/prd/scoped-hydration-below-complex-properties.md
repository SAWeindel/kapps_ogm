# PRD: scoped hydration below a COMPLEX property

**Origin**: wayfinder ticket `EHoffm/kapps_semantic_middleware#78` on map `#57`, grilled 2026-08-07.
**Status**: requirement capture. No `kapps_ogm` code written from this document yet.
**Audience**: `kapps_ogm` maintainer, and whoever picks up `#8`.
**Related**: `#8` (resolve a parameter's interface per instance; select the view by merge depth — the
closest neighbour, see *Relationship to #8* below), `#3` (SHACL support), `#4` (commit relocates blank
nodes), `#6` (skolemisation, closed), `#13` (`OGM.create` cannot derive its ClassScope from data).
The specification precedent is `docs/prd/kapps-ogm-anonymous-node-identity.md` in
`EHoffm/kapps_semantic_middleware`.

## Problem

A `ClassScope` is silently truncated at a `COMPLEX` property. A caller can say *"hydrate
`hasConveyorBelt`, then `hasConveyorSpeed`"*, and cannot say *"…then only `hasValue` and `hasUnit`"*.
The node behind a complex property arrives whole or not at all.

**Four places truncate, and they truncate independently.** All four must change together, or the
halves disagree.

| # | Site | Evidence |
|---|---|---|
| 1 | `PropertySpec._specify_complex_property(cls, prop_iri, ogm)` — `kapps_ogm/mapping/property_spec.py:606` | takes no `class_scope`; hardcodes the nested anonymous `ClassSpec` to `ClassHydrationLevel.FULL` |
| 2 | `OGM._fetch_complex_property(self, instance_iri, property_iri)` — `kapps_ogm/ogm.py:204` | takes no `class_scope`; queries `?bnode ?property ?value`; docstring: *"All properties attached to the complex class are fetched."* |
| 3 | `ClassScope.from_node_data` — `kapps_ogm/utils/class_scope.py:22` | `chains_from_node_data` recurses only into values that are `Node` instances; a complex property's data is a list of plain dicts, so recursion stops at the boundary |
| 4 | `OGM.fetch`'s dispatch — `kapps_ogm/ogm.py:353-368` | `case COMPLEX` passes no scope; `case OBJECT` passes `class_scope.get(prop)` and recurses. Chains cross object properties and stop at complex ones |

Site 4 is the clearest statement of the gap:

```python
case PropertyValueKind.COMPLEX:
    property_data = self._fetch_complex_property(
        instance_iri=instance_iri,
        property_iri=property_spec.iri,            # no class_scope
    )
case PropertyValueKind.OBJECT:
    nested_class_scope = class_scope.get(prop, None) if class_scope else None
    property_data = self._fetch_object_property(
        ..., nested_class_scope=nested_class_scope,  # scope recurses
    )
```

## Motivating case

`kapps_semantic_middleware` runs a factory in which each TransferUnit has its **own** MQTT broker,
and a controller process drives units over REST only. The architectural claim under test is that the
knowledge graph is the only artifact any two units share.

A parameter node for a belt's speed carries both domain content and connection metadata:

```
_:speed  inf:hasValue 1.5 ; tu:hasUnit "m/s" ; inf:accessMode "readwrite" ;
         inf:hasMQTTTopic "TransferUnit1/ConveyorBelt/right/speed" ;
         inf:hasMQTTSetTopic "TransferUnit1/ConveyorBelt/right/speed_set" ;
         inf:hasMQTTBrokerIP "127.0.0.1" ; inf:hasMQTTBrokerPort 18831 .
```

The controller wants `hasValue`, `hasUnit` and `accessMode`. It has no MQTT connector and must not
learn the broker's address. Because the node arrives whole, it holds all seven properties for the
life of the process. Measured live on 2026-08-07, the controller's own HTTP API returns:

```json
"facets": {"hasUnit": "m/s", "hasMQTTBrokerIP": "127.0.0.1", "hasMQTTBrokerPort": 18831,
           "hasMQTTTopic": "TransferUnit1/ConveyorBelt/right/speed", ...}
```

The consumer's present remedy is a middleware-side projection: fetch everything, then delete
(`prune_southbound`, recorded as ADR 0028 in `kapps_semantic_middleware`). **This PRD asks for
"never ask" in place of "fetch then delete."**

## Relationship to `#8`

`#8` (PRD requirements R7–R9 of the anonymous-node document) proposes the **ontology-driven**
answer: the effective nested `ClassSpec` is the union of a property's own range restriction and the
restrictions of the interfaces resolved for that node, and a consumer selects a view by **merge
depth**.

| View | Merges | Contains |
|---|---|---|
| user (northbound) | domain restriction + `inf:isInterfaceAccessibleParameter` | value, unit, access mode |
| wiring (connector) | the above + `inf:isInterfaceAccessible<Protocol>Parameter` | + topic, set topic, broker |

**Both mechanisms fail closed**, which is the property that matters: `#8` because a protocol term
sits on a protocol subproperty nobody merged, this PRD because a caller enumerates what it wants and
a new term is simply not on the list.

They differ in **who decides**:

- `#8` — the ontology decides, so every consumer of a given view agrees by construction, and the
  ontology hierarchy is the contract. Granularity is whatever the hierarchy expresses.
- this PRD — the caller decides, at arbitrary granularity, including ontologies with no interface
  hierarchy to lean on.

**`#8` alone would resolve the motivating case above.** This document is filed as the general
mechanism, not as a competitor. If `#8` lands first, the motivating case closes and the requirements
here stand on their own merits. If both land, `#8` is naturally expressed as a *derived* scope.
**A decision on whether to build one, the other, or both is explicitly deferred and is the first
thing to settle** — see *Open questions*.

## Requirements

**R1 — A scope descends into a complex property.** `ClassScope` already expresses this: a chain
`[tu:hasConveyorSpeed, inf:hasValue]` builds `{hasConveyorSpeed: {hasValue: {}}}` through the public
`from_property_chains`. Nothing in the type needs to change. The four sites above must stop
discarding the nested level.

**R2 — The shape follows the scope.** `_specify_complex_property` accepts the nested scope and
builds the anonymous nested `ClassSpec` from the intersection of the range restriction and that
scope. Properties outside the scope are absent from the spec, not merely unfetched — the projection
must be structural, so a materialised model cannot carry them and `to_triples` cannot emit them.

**R3 — The read follows the scope.** `_fetch_complex_property` accepts the nested scope and
constrains its query to the scoped properties, rather than `?bnode ?property ?value`. A scope naming
two of seven properties costs a query for two.

**R4 — Scope derivation descends too.** `ClassScope.from_node_data` recurses into complex node data.
This is what makes a partial payload self-describing: the scope is re-derived from the data, so it
survives `fetch → model_dump → JSON → transform elsewhere → deserialize → commit` with no state
carried on the `Node`. That round trip is an explicitly supported flow in `kapps_semantic_middleware`
and it is the reason the scope must **not** live as node state.

**R5 — One scope governs spec, read and diff.** Today the three agree by accident, because all three
mean *"everything below a complex property"*. They must agree on purpose. An asymmetry — narrow on
one side of a commit and wide on the other — is the failure mode this requirement exists to prevent.

**R6 — Default behaviour is unchanged in this release.** Omitting a nested scope hydrates the
complex node fully, exactly as today. Every existing caller keeps its behaviour with no edit.

**R7 — Full hydration becomes explicit in the next release.** A caller wanting the whole node passes
a parameter saying so. The default becomes scope-respecting. This is a breaking change and needs a
deprecation path: in this release, emit a deprecation notice on the implicit-full path so callers
can migrate before the default moves.

**R8 — `create` requires a complete node.** Partial hydration is a **read-and-update** concept. A
brand-new node built from partial data genuinely lacks properties a shape may require, and no
merge-with-existing is possible because nothing exists yet. `OGM.create` with a partial scope must
fail loudly rather than write an incomplete node. This interacts with `#3` (SHACL) and `#13`.

## The write path

This is the requirement area with the least evidence behind it, and it is deliberately written as
questions rather than answers.

**What is established:**

- `OGM.commit` derives its scope from the payload (`ClassScope.from_node_data`) and uses the **same**
  derived spec to fetch the old node (`kapps_ogm/ogm.py:437-444`). The two sides of the diff are
  therefore already symmetric by construction — the asymmetry R5 guards against is not present today.
- Skolemisation (`#6`, shipped) gives a parameter node an IRI rather than a `BNode`. In
  `kapps_triplestore_interface.utils.group_triples_by_bnode`, a triple containing no blank node becomes its
  own group (`utils.py:377-380`). So the whole-group DELETE/INSERT that motivated `#4` does not apply
  to skolemised parameter nodes; the diff is per-triple.

**What is not established, and must be settled by experiment before implementation:**

- Whether `Node.to_triples` emits nothing for a property that the `ClassSpec` declares but the data
  omits. If it does, a partial payload leaves untouched properties on neither side of the diff and
  they survive. If it does not, a partial payload deletes them. **This single behaviour decides
  whether R1–R5 are safe or dangerous on the write path**, and it should be answered with a live
  round-trip test before any code is written.
- Whether a scoped read followed by an unscoped commit (or the reverse) is reachable through the
  public API, and what should happen if it is.

## Non-goals

- Replacing `#8`. See *Relationship to `#8`*.
- SHACL shape authoring or validation. Deferred with `#3`.
- Entity deletion, still intentionally unsupported.
- Scoping anything other than the node behind a `COMPLEX` property. Object-property scoping already
  works.
- Changing `prune_southbound` in `kapps_semantic_middleware`. That projection stays until this
  capability or `#8` lands; retiring it is downstream work, not part of this requirement.

## Open questions

1. **Build this, `#8`, or both?** `#8` is the better fit for the northbound/southbound split because
   the ontology governs it and all consumers agree. This PRD is the more general mechanism. They are
   not mutually exclusive; `#8` can be expressed as a derived scope once R1–R5 exist.
2. **Does `to_triples` emit declared-but-absent properties?** See *The write path*. Blocking.
3. **Does the deprecation notice in R7 belong on `fetch`, on `get_class_spec`, or on both?**
4. **What is the migration story for `hydration_level`?** `ClassHydrationLevel` already has
   `REFERENCE` / `SCOPE` / `FULL`, and `_specify_complex_property` hardcodes `FULL`. R6/R7 may be
   expressible as making that hardcoded value follow the caller's `hydration_level` rather than
   adding a new parameter. This is the cheapest possible shape for the change and should be
   evaluated first.

## Process note

`kapps_semantic_middleware`'s root ADR 0001 permits only **bugfixes** in sibling checkouts, and root
ADR 0003 states that the `kapps_ogm` checkout stays unpatched so it can track upstream. This is a new
capability, so it is specified here and handed over rather than patched downstream. Implementation in
this repository was authorised by Etienne Hoffmann on 2026-08-07; the downstream ADRs are stale and
are being amended to record that.
