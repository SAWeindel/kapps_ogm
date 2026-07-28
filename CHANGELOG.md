# Changelog

## Unreleased

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
