# Changelog

## Unreleased

### Added

- **Four new modules implement Skolemised identity for anonymous nodes, per
  SAWeindel/kapps_ogm#6 and PRD requirements R1–R6.** The specification lives at
  `docs/prd/kapps-ogm-anonymous-node-identity.md` in `EHoffm/kapps_semantic_middleware`.
  `kapps_ogm/utils/skolem.py` provides `mint_skolem_iri()` and `is_skolem_iri()`, plus
  `WELL_KNOWN_GENID_PATH` and `DEFAULT_SKOLEM_NAMESPACE`. The path begins
  `/.well-known/genid/` per RDF 1.1 Concepts §3.5's recognisability provision, so a third
  party can tell the IRI stands in for a blank node; the minting authority is an
  ontology-governance decision not yet settled, so the namespace is configurable per `OGM`
  instance via a new `skolem_namespace` constructor argument and the default is documented
  as a placeholder. `kapps_ogm/mapping/anonymous_model.py` introduces `AnonymousNodeModel`,
  wired through the existing `ClassSpec.pydantic_base_model` seam; it carries the node's
  address in a pydantic `PrivateAttr`, captured from the payload's `id` key by a
  `mode="wrap"` model validator that pops the key before field validation. Verified on
  pydantic 2.13: private attributes are absent from `model_dump()`, `model_dump_json()`
  and `model_json_schema()`, so the address cannot leak northbound, into OpenAPI, or into
  `to_triples`; it does not survive a dump-then-revalidate round trip, which is why it is
  a mirror and `Node.data` remains the authoritative carrier. `kapps_ogm/node/node_address.py`
  exports `reconcile_anonymous_addresses()`, which copies addresses from the fetched node
  onto the node about to be written. `kapps_ogm/utils/errors.py` adds
  `AnonymousNodeFetchError` and `UnresolvableNodeAddressError`.

### Fixed

- **Anonymous nodes lost their identity on every write; they are now Skolemised.** The
  anonymous node behind a `COMPLEX` property — every parameter node in the Circular Factory
  — had no identity that survived a write. Identity was destroyed three times over:
  `OGM._fetch_complex_property` (`ogm.py`) grouped the query result by node and then
  returned `list(property_data_dict.values())`, discarding the key, so identity died at
  read; `format_for_instance` called `_assign_id`, which for an anonymous ClassSpec minted
  `db.new_blank_id()`, but pydantic ignored the `id` key entirely because an anonymous
  model has no `id` field; and `_value_to_triples` (`node_serializer.py`) minted another
  fresh `BNode` for any nested model without an `id` — on both sides of the diff. `Node.diff`
  therefore compared blank-node groups whose labels never matched, so a commit deleted the
  whole old group and inserted a new one. Because `graph_db_interface.triples_update`
  renders blank nodes as SPARQL variables, the DELETE matched the real node by structure,
  unlinking it and orphaning every triple the ClassSpec did not declare. A no-change commit
  was not a no-op. This was reproduced live on the ticket: after committing a speed value,
  the parameter node had moved, and three MQTT connection-metadata triples were left on a
  node with no inbound edge — while the call reported success.

  The fix skolemises. A blank node is an existential variable: it has no extent, cannot be
  addressed, and can only be re-found by matching a pattern from a named subject — which is
  exactly what made the write destructive. RDF 1.1 Concepts §3.5 sanctions replacing it with
  a Skolem IRI: the transformation does not appreciably change the meaning of an RDF graph,
  and it permits the possibility of other graphs subsequently using the Skolem IRIs, which
  is not possible for blank nodes. That second property is the requirement — PROV
  qualification, SHACL focus nodes and joining a history snapshot to live state are all
  impossible against a blank node. Two conditions attach to the guarantee and are honoured
  as normative rules: the IRIs are globally unique and never reused, and nothing is asserted
  about the node — no `rdf:type`, no class membership, no annotation. `to_triples` already
  satisfied the type half, since it emits type triples only when `class_spec.iri` is set and
  an anonymous ClassSpec has `iri=None`.

  `_fetch_complex_property` now keeps the identifier it already had, returning it as an
  `"id"` entry per group, and returns groups sorted by identifier so two fetches of
  unchanged data align positionally; `sanitize_data` passes an `IRI` or `BNode` through
  verbatim instead of coercing it. `_assign_id` mints a Skolem IRI for an anonymous
  ClassSpec instead of `db.new_blank_id()`. `_value_to_triples` no longer mints at all; it
  resolves the target in order — the address recorded in `Node.data`, then the `_node_iri`
  mirror on the model — otherwise it raises `UnresolvableNodeAddressError`. An unresolvable
  target must never silently become a new node. `OGM.commit` now fetches the old node before
  materializing the new one and reconciles addresses between them; this is load-bearing
  rather than incidental, since the canonical usage pattern is `fetch(materialize=True)` →
  `model_dump()` → edit → `commit(data=<plain dict>)`, and the dump deliberately carries no
  address, so it must be recovered from the store side. `OGM.fetch` on a Skolem IRI now
  raises `AnonymousNodeFetchError` naming the situation ("anonymous node — fetch its parent")
  before touching the database, rather than failing later with `ValueError: Could not
  determine class IRI`. The diff needed no change: with an IRI subject,
  `group_triples_by_bnode` puts each triple in its own group, so the diff reduces to what
  actually changed and stays one atomic DELETE/INSERT.

  A parameter node already in the store as a real blank node is relocated once, to a Skolem
  IRI, on the next write that touches it; the old side of that one transaction still names
  the blank node, so the relocation is a single atomic DELETE/INSERT. Undeclared triples on
  such a node are not carried across that one relocation — the ClassSpec does not know about
  them — so a legacy node loses them exactly once. This is bounded in practice because only
  the TBox is seeded in productive environments; all ABox data is written through the OGM
  and is therefore skolemised from the outset. Converting a whole resource up front, and the
  inverse deskolemise, are #9 (PRD R12). Merging the interface restrictions so that
  connection metadata becomes declared — which is what stops even that one-time loss — is
  #7 (PRD R7). Entity deletion stays unsupported; canonical (isomorphism-preserving)
  Skolemisation is explicitly not what was built, since identity here is per node, not
  derived from content, which is what a locator needs.

  Five new unit test files, 72 tests, all offline against the existing `mock_db` fixture:
  `test_skolem_identity.py` (minting, recognition, the fetch guard),
  `test_anonymous_node_model.py` (projection invariance), `test_anonymous_node_addressing.py`
  (`to_triples` address resolution), `test_anonymous_node_round_trip.py` (identity at read,
  reconciliation, `Node.diff`), and `test_commit_round_trip.py`, which drives the full
  `fetch` → `model_dump` → edit → `commit` pattern and asserts the ticket's acceptance
  criteria directly: an unchanged commit writes zero triples, a changed value emits exactly
  one DELETE and one INSERT naming the node's IRI, the belt→parameter link is never
  unlinked, and no blank node reaches the write path. The suite is 155 tests, all passing.
  The ticket noted that this was never caught because `scripts/demo_update_value.py`
  exercises only the named-class `OBJECT` path — `demo:hasConveyorPosition` has a named-class
  range, so `_value_to_triples` took the stable-IRI branch. The `COMPLEX` update path now
  has coverage.

- **Review follow-ups, all in the same change.** `mint_skolem_iri` accepted any namespace while
  `is_skolem_iri` required the literal `/.well-known/genid/` path, so an `OGM` configured with a
  namespace off the default minted addresses its own guard could not recognise — silently
  disarming the `AnonymousNodeFetchError` check in `OGM.fetch`. `validate_skolem_namespace` now
  normalises the trailing slash and rejects a namespace lacking the well-known path, at `OGM`
  construction rather than on the first anonymous write; only the authority preceding that path
  was ever configurable, since §3.5 fixes the path itself.

  `to_json_ld` decided what to inline by testing `startswith("genid-")`, the blank-node label
  form, so a skolemised parameter stopped being inlined and its address surfaced in a northbound
  projection — a leak R4 forbids, and a change to the served shape. All five inlining decisions
  now route through one `is_anonymous_ref` predicate that treats a Skolem IRI as what §3.5 says
  it is: a blank node's stand-in.

  `reconcile_anonymous_addresses` aligns anonymous values by position, which is unambiguous for
  an appended or edited list but not for a shortened one: nothing says which stored node was
  dropped, and aligning by position would shift a surviving node's address onto the wrong entry,
  moving one parameter's properties onto another parameter's node. That is a worse failure than
  losing an address, so it now raises `AmbiguousNodeAlignmentError` rather than guessing.
  Clearing a property entirely stays legal — there is nothing left to misassign. Reordering an
  equal-length list is still undetectable from position alone and is documented as such; closing
  it needs content-based matching, which is not warranted while parameter properties are
  effectively single-valued.

  `kapps_ogm/utils/__init__.py` now re-exports the new errors and Skolem helpers, matching how
  `constants`, `pretty_print`, `json_ogm_encoder` and `class_scope` are already surfaced.

- **`ogm.py` called `format_triples_turtle` without importing it, so `OGM.commit` raised
  `NameError` whenever the logger was enabled for `DEBUG`.** The call sits inside an
  `isEnabledFor(DEBUG)` guard, which is why it had gone unnoticed: the suite never
  commits at `DEBUG`. Found by static analysis while reordering `commit`, not by hitting it.
  Added the missing import.

### Removed

- **`tests/integration/test_roundtrip.py`, the repository's only integration test,
  pending the semantic middleware rebuild.** It asserted the OGM's round-trip
  identity contract — `create(persist=True)` followed by `fetch(materialize=True)`
  yields the same JSON-LD — and in doing so was also the only executable
  demonstration of how `kapps_semantic_middleware` drives the OGM. Removed for two
  reasons: its shape (a hand-built `ClassScope` from two depth-1 property chains,
  passed to both `create` and `fetch`) encodes the *previous* middleware's call
  pattern, which pins the OGM interface while its only real consumer is being
  rebuilt; and it never reached its own assertion, failing instead inside
  `ogm.create` on the unrelated defect tracked as #13. A permanently-red test that
  fails before the property it exists to check asserts nothing.

  The contract and the demonstration role are both still wanted: reinstating them
  against the rebuilt middleware is tracked as #16, which carries the removed source
  verbatim for reconstruction. Its fixture data,
  `tests/test_data/TransferUnit1_data.json`, is deliberately retained and is
  currently unreferenced.

  `deepdiff` remains a declared dev dependency — `tests/unit/test_class_scope.py`
  still uses it.

- **`scripts/demo_instantiation.py`, for the same reason, and because it was the
  last consumer of undeclared packages.** It was the repository's most complete
  worked example — the only one going all the way from an ontology class to a served
  REST API: `ClassScope.from_property_chains` → `ClassSpec.specify` →
  `to_pydantic_model` → `create_blank_instance` → `ogm.create` (in-memory *and*
  persisted to a named graph) → `materialize` → `to_triples` / `to_json_ld` →
  `aas.DataModel.from_models` → `generate_rest_api_for_data_model` → `uvicorn.run`.

  Only that last stretch needed `aas_middleware` and `uvicorn`, and neither is
  declared in `pyproject.toml`; `aas_middleware` was deliberately dropped in 279851e
  ("This will break demos"). Once #15 was fixed, this script was the only thing in
  the repository that still could not be run from a clean environment built from the
  manifest — **with it gone, every remaining script and test can.** It also encoded
  the previous middleware's call pattern and carried a hardcoded GraphDB hostname.

  Reinstatement is split in two, because the demo must in future drive
  `kapps_semantic_middleware` rather than construct `aas_middleware` directly — and
  that half cannot live in this repository, since the middleware already depends on
  `kapps_ogm` and a demo here driving it would close a dependency cycle. The OGM-only
  portion is #17 and is blocked on nothing; the end-to-end portion is
  `EHoffm/kapps_semantic_middleware#56`. The four generated artefacts under
  `scripts/output/` are retained for reference and are now stale and unreferenced.

### Fixed

- **The test suite could not be installed or run from the manifest: two packages
  imported at module scope were declared nowhere in `pyproject.toml`.** Because a
  missing import at module scope is a pytest *collection* error rather than a test
  failure, either one alone aborted the entire run — including the 80-odd tests that
  never touch the missing package. No environment built from the manifest could run
  the suite at all, which blocked verifying any other ticket. Two distinct defects,
  the first masking the second:

  1. **`deepdiff` was imported but never declared** (`pyproject.toml`). Used by
     `tests/unit/test_class_scope.py` (`from deepdiff import DeepDiff`),
     `tests/integration/test_roundtrip.py` and `scripts/demo_roundtrip.py` (both
     `import deepdiff`), but absent from both `[tool.poetry.dependencies]` and
     `[tool.poetry.group.dev.dependencies]`, which listed only `black`, `pytest` and
     `pylint`. Declared `deepdiff = "^9.1.0"` in the dev dependency group.

  2. **The root `conftest.py` imported the deliberately removed `aas_middleware`**
     (`tests/conftest.py`). A root `conftest.py` is imported before any test module,
     so this had exactly the same suite-wide blast radius as (1) — it was simply
     masked by it. The import served only a session-scoped `mw` fixture returning a
     bare `AasMiddleware()`, which no test in the repository requests: dead code left
     behind when commit 279851e dropped `aas_middleware` from the manifest. Removed
     the unused fixture and its import, rather than re-adding a dependency that had
     been intentionally removed.

  Verified by building a clean virtual environment from the manifest alone, rather
  than relying on a developer machine that has accumulated packages. The suite now
  collects all 84 tests with zero collection errors, and 83 pass. The one remaining
  failure, `test_roundtrip[…TransferUnit…]`, is a pre-existing product defect
  unrelated to packaging and already tracked as #13: `OGM.create` raises from
  `_recursive_update_nodes_class_spec` (`kapps_ogm/node/core.py`) because the
  `ClassScope` built from the test's property chains does not cover the `isOccupied`
  property present in the data. It aborts inside `ogm.create`, well before any
  `DeepDiff` call.

  Note for follow-up: `scripts/demo_instantiation.py` still does `import
  aas_middleware`, and is now the only consumer of an undeclared package left in the
  repository. That is the breakage commit 279851e knowingly accepted ("This will
  break demos"), and `scripts/` is outside this fix's scope, but it means the demos
  are still not runnable from the manifest alone. Reported as #15 and fixed here.

- **`OGM.commit` could not add or remove properties — only replace equal counts,
  and crashed on any `xsd:dateTime` property.** Three related defects, all on the
  commit path, which together made the OGM unusable as a general write path
  (contradicting the paper's "single validated write path" and the OGM's own
  documented triple-level mutability):

  1. **`OGM.commit` crashed on entities with a `datetime` value**
     (`kapps_ogm/ogm.py`). Leftover debug `print(json.dumps(...))` statements tried
     to serialize the diff (JSON-LD) with a `datetime` literal in it, raising
     `TypeError: Object of type datetime is not JSON serializable`. Removed the
     debug prints; replaced with a single `logger.debug` of the triple counts.

  2. **`ClassScope.from_node_data` dropped empty-valued properties**
     (`kapps_ogm/utils/class_scope.py`). A property whose value list was empty
     (`{prop: []}`, the idiom for "remove this property") produced no scope entry,
     because the inner `for value in values` loop never ran. `OGM.commit` therefore
     derived a scope that omitted the property, fetched the old state without it,
     and never diffed it away — so property *removal* was impossible. Fixed to emit
     a leaf chain for empty-valued properties so the scope covers them.

  3. **`OGM.commit` used `db.triples_update`, which required equal-length lists.**
     A general diff (from `Node.diff`) has disjoint remove/add sets of differing
     size, so add-only and remove-only commits raised
     `InvalidInputError: Old and new triples lists must have the same length.`
     Kept `triples_update` (its single atomic `DELETE/INSERT` transaction is
     required for SHACL-safe cardinality replacement — e.g. a possession handover)
     and generalized `graph_db_interface.triples_update` to accept unequal lengths
     (see that repo's changelog).

  Together these make `OGM.commit` able to add, remove, and replace properties
  atomically. Reported/fixed by the `kapps_semantic_middleware` project (which
  routes all of its knowledge-graph writes through the OGM) per its
  dependency-and-bugfix policy.

- **`PropertySpec.specify()` crashed with `NameError` on every property whose range
  needed resolving** (`kapps_ogm/mapping/property_spec.py`).

  **Symptom:** any call that resolves a class's properties —
  `OGM.get_class_spec(...)`, `OGM.create(...)`, `OGM.fetch(...)` (when a class spec
  must be derived), and `OGM.commit(...)` — raised
  `NameError: name 'range_query_result' is not defined` as soon as it reached a
  property with an `rdfs:range`. In practice this broke nearly every real
  fetch/create/commit, since almost every class has at least one such property. Only
  `ClassHydrationLevel.REFERENCE` (or an empty scope), which skips property
  resolution, avoided the crash.

  **Root cause:** commit `bcb7840` ("Fix handling of owl:Thing range in
  propertySpec") refactored the range lookup so the query result is bound to the
  local variable `query_result`, but the immediately following set-comprehension was
  left referencing the old, now-undefined name `range_query_result`:

  ```python
  query_result = ogm.db.triples_get(
      sub=prop_iri, pred="rdfs:range", include_implicit=True
  )
  range_set = set(triple[2] for triple in range_query_result)  # NameError
  ```

  **Fix:** reference the correct variable, `query_result`:

  ```python
  range_set = set(triple[2] for triple in query_result)
  ```

  This is a one-line correctness fix with no behavioral change beyond making the
  intended code path run. No public API, signature, or data-shape change.

  **Reported/fixed by:** the `kapps_semantic_middleware` project, which depends on
  `kapps_ogm` as a local editable dependency and hit this on its first real
  fetch/commit. Per that project's dependency-and-bugfix policy
  (`kapps_semantic_middleware/docs/adr/0001-dependency-wiring-and-bugfix-policy.md`),
  genuine correctness bugs in sibling dependency repos are fixed directly in the
  sibling, with a detailed changelog entry — this is that entry.
