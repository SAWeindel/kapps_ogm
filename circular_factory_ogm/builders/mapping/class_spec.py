from typing import Optional, Type, Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field
import logging
import pydantic as pd
from graph_db_interface import IRI, SPARQLQuery
from graph_db_interface.utils.processing import process_bindings_select
from .property_spec import (
    process_literal_property,
    process_class_property,
    process_complex_property,
)

from ...utils.constants import (
    FUNDAMENTAL_CONCEPTS as fc,
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)

if TYPE_CHECKING:
    from .property_spec import PropertySpec
    from ...ogm import OGM
    from ...node import Node
    from ...utils.pretty_print import class_spec_to_string

logger = logging.getLogger(__name__)


@dataclass
class ClassSpec:
    iri: Optional[IRI]
    label: Optional[str] = None
    properties: Dict[IRI, "PropertySpec"] = field(default_factory=dict)
    types: List[IRI] = field(default_factory=list)
    superclasses: List[IRI] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _hydrated: bool = field(default=False, init=False)

    def to_string(self) -> str:
        from ...utils.pretty_print import class_spec_to_string

        return class_spec_to_string(self)

    def hydrate(self, ogm: "OGM") -> "ClassSpec":
        """
        Populate this ClassSpec with all details from the ontology.
        Uses `specify` internally and updates this instance in place.
        Returns self
        """
        if not self.iri:
            raise ValueError("Cannot hydrate ClassSpec without an IRI.")

        hydrated_spec = specify(self.iri, ogm)
        self.label = hydrated_spec.label
        self.properties = hydrated_spec.properties
        self.types = hydrated_spec.types
        self.superclasses = hydrated_spec.superclasses
        self.metadata = hydrated_spec.metadata
        self._hydrated = True
        return self

    def to_pydantic_model(self) -> Type[pd.BaseModel]:
        """
        Convert ClassSpec into a Pydantic model using PropertySpec.to_pydantic_field().
        """
        fields: Dict[str, tuple[Any, Any]] = {}
        iri_field_map: Dict[str, str] = {}
        for prop_iri, prop_spec in self.properties.items():
            # Use sanitized IRI token (lined) for field names to satisfy Pydantic
            field_name = getattr(prop_iri, "lined", None) or str(prop_iri).replace("/", "_").replace("#", "_")
            fields[field_name] = prop_spec.to_pydantic_field()
            iri_field_map[field_name] = str(prop_iri)
        # Use sanitized IRI token (lined) for model name as well
        model_name = getattr(self.iri, "lined", None) or str(self.iri).replace("/", "_").replace("#", "_")
        model_cls = pd.create_model(model_name, __base__=pd.BaseModel, **fields)  # type: ignore[arg-type]
        # Attach mapping from sanitized field names to full IRIs for downstream use
        setattr(model_cls, "_iri_fields", iri_field_map)
        setattr(model_cls, "_iri_model_name", str(self.iri))
        return model_cls


def specify(
    class_iri: IRI,
    ogm: "OGM",
    property_chain: Optional[list[IRI]] = None,
) -> ClassSpec:
    """
    create a ClassSpec for the given IRI by analyzing its RDF data in the GraphDB via the OGM instance.

        Args:
            iri: The IRI of the class to specify
            ogm: The OGM instance with access to the GraphDB
        Returns:
            A ClassSpec instance representing the class specification"""
    db = ogm.db

    # first we get all types of the class
    triples = db.triples_get(sub=class_iri, pred=fc["RDF_TYPE"], include_implicit=True)
    class_types = [triple[2] for triple in triples]
    if fc["OWL_CLASS"] not in class_types and fc["RDFS_CLASS"] not in class_types:
        raise ValueError(f"IRI {class_iri} is not an OWL/RDFS Class.")

    class_spec = ClassSpec(iri=class_iri)
    class_spec.types = class_types

    label_triples = db.triples_get(
        sub=class_iri, pred=fc["RDFS_LABEL"], include_implicit=True
    )
    if label_triples:
        class_spec.label = str(label_triples[0][2])

    superclasses = [
        triple[2]
        for triple in db.triples_get(
            sub=class_iri, pred=fc["RDFS_SUBCLASS_OF"], include_implicit=True
        )
    ]
    if class_iri in superclasses:
        superclasses.remove(class_iri)
    else:
        logger.warning(
            f"{class_iri} should be implicitely a subclass of itself but is not found in rdfs:subClassOf."
        )
    if superclasses:
        class_spec.superclasses = superclasses

    # 1) inherit properties from superclasses (keep first occurrence)
    class_spec.properties = {}
    for sc in superclasses:
        inherited = classify_outgoing_properties(sc, ogm)
        for k, v in inherited.items():
            if k not in class_spec.properties:
                class_spec.properties[k] = v

    # 2) own properties override inherited ones
    own_props = classify_outgoing_properties(class_iri, ogm)
    class_spec.properties.update(own_props)

    print(f"Specifying class {class_iri} as {class_spec.to_string()}")

    return class_spec


def classify_outgoing_properties(
    class_iri: IRI, ogm: "OGM"
) -> dict[IRI, "PropertySpec"]:
    db = ogm.db

    properties = [
        triple[0]
        for triple in db.triples_get(
            pred=fc["RDFS_DOMAIN"], obj=class_iri, include_implicit=True
        )
    ]
    property_spec_dict: dict[IRI, PropertySpec] = {}
    for prop in properties:
        ### first we categorize the property regarding its type and characteristics
        # query for property type
        query_result = db.triples_get(
            sub=prop, pred=fc["RDF_TYPE"], include_implicit=False
        )
        property_types = [triple[2] for triple in query_result]

        if not property_types:
            raise ValueError(f"Property {prop} has no rdf:type defined.")

        # Categorize property types and check if functional property
        base_types = []
        characteristics = []

        for ptype in property_types:
            if ptype in PROPERTY_TYPES:
                base_types.append(PROPERTY_TYPES[ptype])
            elif ptype in PROPERTY_CHARACTERISTICS:
                characteristics.append(PROPERTY_CHARACTERISTICS[ptype])

        ### while the domain is clear (the node we are analyzing) the range needs to be analyzed
        sparql_query = f"""
        SELECT ?rangeType
        WHERE {{
            BIND(<{str(prop)}> AS ?property) .
            ?property <{fc['RDFS_RANGE']}> ?range .
            BIND(IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2000/01/rdf-schema#Datatype> }}, "literal",
                IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2002/07/owl#DatatypeProperty> }}, "literal",
                IF((EXISTS {{ ?range <{fc['RDF_TYPE']}> <{fc['OWL_CLASS']}> }} || EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2000/01/rdf-schema#Class> }} ) && isIRI(?range), "class",
                IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2002/07/owl#Restriction> }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#intersectionOf> ?x }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#unionOf> ?y }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#complementOf> ?z }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#oneOf> ?w }},
                    "complex",
                    "unknown"
                )))) AS ?rangeType)
        }}
        """

        query_result = db.query(sparql_query)
        range_types = [
            binding["rangeType"]["value"]
            for binding in query_result["results"]["bindings"]
        ]

        property_spec = None
        if range_types:
            match range_types[0]:
                case "literal":
                    property_spec = process_literal_property(ogm, prop)
                case "class":
                    property_spec = process_class_property(ogm, prop)
                case "complex":
                    property_spec = process_complex_property(ogm, prop)
                case _:
                    logging.warning(f"Unknown range type for property {prop}")

        # Apply characteristics to the property_spec if it exists
        if property_spec and "functional" in characteristics:
            property_spec.max_count = 1

        if property_spec:
            print(f"Processed property {prop}: {property_spec.to_string()}")
            property_spec_dict[prop] = property_spec

    print(f"Final model data properties: {property_spec_dict}")
    return property_spec_dict
