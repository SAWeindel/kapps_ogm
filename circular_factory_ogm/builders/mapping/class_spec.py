from __future__ import annotations

from typing import Optional, Type, Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field
import logging
import pydantic as pd

from graph_db_interface import IRI
from circular_factory_ogm.utils.pretty_print import class_spec_to_string
from circular_factory_ogm.utils.constants import (
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)

from circular_factory_ogm.builders.mapping.property_spec import PropertySpec

if TYPE_CHECKING:
    from circular_factory_ogm.ogm import OGM

logger = logging.getLogger(__name__)


@dataclass
class ClassSpec:
    iri: Optional[IRI]
    label: Optional[str] = None
    properties: Dict[IRI, PropertySpec] = field(default_factory=dict)
    types: List[IRI] = field(default_factory=list)
    superclasses: List[IRI] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _hydrated: bool = field(default=False, init=False)

    def to_string(self) -> str:

        return class_spec_to_string(self)

    def hydrate(self, ogm: "OGM") -> ClassSpec:
        """
        Populate this ClassSpec with all details from the ontology.
        Uses `specify` internally and updates this instance in place.
        Returns self
        """
        if not self.iri:
            raise ValueError("Cannot hydrate ClassSpec without an IRI.")

        hydrated_spec = ClassSpec.specify(self.iri, ogm)
        self.label = hydrated_spec.label
        self.properties = hydrated_spec.properties
        self.types = hydrated_spec.types
        self.superclasses = hydrated_spec.superclasses
        self.metadata = hydrated_spec.metadata
        self._hydrated = True
        return self

    def to_pydantic_model(self) -> Type[pd.BaseModel]:
        """
        Convert ClassSpec into a Pydantic model.
        Delegates to PropertySpec.to_pydantic_field() for consistent field generation.
        """
        fields: Dict[str, tuple[Any, Any]] = {}

        for prop_iri, prop_spec in self.properties.items():
            # Use sanitized IRI for field names
            field_name = prop_iri.lined

            # Delegate to PropertySpec for field generation (includes validators via Annotated types)
            field_type, field = prop_spec.to_pydantic_field()
            fields[field_name] = (field_type, field)

        # Build the Pydantic model
        model_name = (
            self.iri.lined if self.iri else "AnonymousClass"
        )  # TODO: use graphdbs blanknode generator?
        model_cls = pd.create_model(model_name, __base__=(pd.BaseModel,), **fields)  # type: ignore[call-overload] #TODO: is baseModel correct base here?

        # Keep mapping to IRIs for reference
        setattr(
            model_cls,
            "_iri_fields",
            {prop_iri.lined: prop_iri for prop_iri in self.properties.keys()},
        )
        setattr(model_cls, "_iri_model_name", self.iri if self.iri else None)

        return model_cls

    @classmethod
    def specify(
        cls,
        class_iri: IRI,
        ogm: "OGM",
        property_chains: Optional[list[list[IRI]]] = None,
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
        triples = db.triples_get(sub=class_iri, pred="rdf:type", include_implicit=True)
        class_types = [triple[2] for triple in triples]
        if IRI("owl:Class") not in class_types and IRI("rdfs:Class") not in class_types:
            raise ValueError(f"IRI {class_iri} is not an OWL/RDFS Class.")

        class_spec = cls(
            iri=class_iri,
            types=class_types,
        )

        label_triples = db.triples_get(
            sub=class_iri, pred="rdfs:label", include_implicit=True
        )
        if label_triples:
            class_spec.label = str(label_triples[0][2])

        superclasses = [
            triple[2]
            for triple in db.triples_get(
                sub=class_iri, pred="rdfs:subClassOf", include_implicit=True
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
            inherited = ClassSpec.classify_outgoing_properties(sc, ogm)
            for k, v in inherited.items():
                if k not in class_spec.properties:
                    class_spec.properties[k] = v

        # 2) own properties override inherited ones
        own_props = ClassSpec.classify_outgoing_properties(class_iri, ogm)
        class_spec.properties.update(own_props)

        if property_chains:
            for property_chain in property_chains:
                current_spec = class_spec
                for i, prop_iri in enumerate(property_chain):
                    if prop_iri not in current_spec.properties:
                        raise ValueError(
                            f"Property {prop_iri} not found in class {current_spec.iri} "
                            f"while processing property chain."
                        )

                    prop_spec = current_spec.properties[prop_iri]

                    if prop_spec.nested is None:
                        raise ValueError(
                            f"Property {prop_iri} has no nested ClassSpec "
                            f"(cannot continue property chain)."
                        )

                    # Rebuild nested ClassSpec with remaining chain tail
                    remaining_chain = property_chain[i + 1 :]
                    nested_spec = cls.specify(
                        class_iri=prop_spec.nested.iri,
                        ogm=ogm,
                        property_chains=[remaining_chain] if remaining_chain else None,
                    )
                    # Mark as hydrated since it was fully specified
                    nested_spec._hydrated = True

                    # Replace nested spec for this chain only
                    prop_spec.nested = nested_spec
                    current_spec = nested_spec

        # Mark as hydrated if it was fully specified
        class_spec._hydrated = True
        print(f"Specifying class {class_iri} as {class_spec.to_string()}")

        return class_spec

    @staticmethod
    def classify_outgoing_properties(
        class_iri: IRI,
        ogm: "OGM",
    ) -> dict[IRI, PropertySpec]:
        db = ogm.db

        properties = [
            triple[0]
            for triple in db.triples_get(
                pred="rdfs:domain", obj=class_iri, include_implicit=True
            )
        ]
        property_spec_dict: dict[IRI, PropertySpec] = {}
        for prop in properties:
            ### first we categorize the property regarding its type and characteristics
            # query for property type
            query_result = db.triples_get(
                sub=prop, pred="rdf:type", include_implicit=False
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
                BIND({prop.n3()} AS ?property) .
                ?property <http://www.w3.org/2000/01/rdf-schema#range> ?range .
                BIND(
                    IF( EXISTS {{ ?range <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2000/01/rdf-schema#Datatype> }}
                        || EXISTS {{ ?range <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#DatatypeProperty> }} ,
                        "literal" ,
                    IF(( EXISTS {{ ?range <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Class> }}
                         || EXISTS {{ ?range <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2000/01/rdf-schema#Class> }}
                       ) && isIRI(?range) ,
                        "class" ,
                    IF( EXISTS {{ ?range <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Restriction> }}
                        || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#intersectionOf> ?x }}
                        || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#unionOf> ?y }}
                        || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#complementOf> ?z }}
                        || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#oneOf> ?w }} ,
                        "complex" ,
                    # DEFAULT
                        "unknown"
                    ))) AS ?rangeType
                )
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
                        property_spec = PropertySpec.specify_literal_property(ogm, prop)
                    case "class":
                        property_spec = PropertySpec.specify_class_property(ogm, prop)
                    case "complex":
                        property_spec = PropertySpec.specify_complex_property(ogm, prop)
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
