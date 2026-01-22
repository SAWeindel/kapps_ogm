from __future__ import annotations

from typing import Optional, Type, Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
import logging
import pydantic as pd

from pydantic import ConfigDict  # Pydantic v2


from graph_db_interface import IRI
from circular_factory_ogm.utils.pretty_print import format_class_spec
from circular_factory_ogm.mapping.property_spec import PropertySpec, PropertyValueKind

if TYPE_CHECKING:
    from circular_factory_ogm.ogm import OGM

logger = logging.getLogger("cf_cspec")


@dataclass
class ClassSpec:
    iri: Optional[IRI]
    label: Optional[str] = None
    comment: Optional[str] = None
    properties: Dict[IRI, PropertySpec] = field(default_factory=dict)
    types: List[IRI] = field(default_factory=list)
    superclasses: List[IRI] = field(default_factory=list)
    pydantic_base_model: Optional[Type[pd.BaseModel]] = pd.BaseModel
    metadata: Dict[str, Any] = field(default_factory=dict)
    _hydrated: bool = field(default=False, init=False)

    def to_string(self) -> str:
        return format_class_spec(self)

    def hydrate(self, ogm: "OGM") -> ClassSpec:
        """
        Populate this ClassSpec with all details from the ontology.
        Uses `specify` internally and updates this instance in place.
        Returns self
        """
        if not self.iri:
            raise ValueError("Cannot hydrate ClassSpec without an IRI.")

        hydrated_spec = ClassSpec.specify(self.iri, ogm)
        for key, value in asdict(hydrated_spec).items():
            setattr(self, key, value)
        return self

    def to_pydantic_model(self) -> Type[pd.BaseModel]:
        """
        Convert ClassSpec into a Pydantic model.
        Delegates to PropertySpec.to_pydantic_field() for consistent field generation.
        """
        fields: Dict[str, tuple[Any, Any]] = {}

        # Only add id field for named classes (not blank nodes)
        if self.iri:
            logger.debug(
                f"Converting ClassSpec '{self.iri.fragment}' to pydantic model"
            )
            fields["id"] = (IRI, pd.Field(..., description="IRI of the instance"))
        else:
            logger.debug(
                "Converting ClassSpec without IRI to pydantic model; this is a blank node that will not be a standalone node."
            )

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
        model_cls = pd.create_model(
            model_name,
            __base__=(self.pydantic_base_model,),
            **fields,
        )  # type: ignore[call-overload] #TODO: is baseModel correct base here?

        # Enforce no unknown properties at model level (replaces Node._validate_data unknown-check)
        if ConfigDict is not None:
            model_cls.model_config = ConfigDict(extra="forbid")
        else:
            class Config(getattr(self.pydantic_base_model, "Config", object)):
                extra = "forbid"

            model_cls.Config = Config

        # Keep mapping to IRIs for reference
        setattr(
            model_cls,
            "_iri_fields",
            {prop_iri.lined: prop_iri for prop_iri in self.properties.keys()},
        )
        setattr(model_cls, "_iri_model_name", self.iri if self.iri else None)

        return model_cls

    @classmethod
    def specify_from_instance(
        instance: pd.BaseModel,
        ogm: "OGM",
    ) -> ClassSpec:
        """
        create a ClassSpec for the given Pydantic model by analyzing its RDF data in the GraphDB via the OGM instance.

            Args:
                model_cls: The Pydantic model class to specify
                ogm: The OGM instance with access to the GraphDB
            Returns:
                A ClassSpec instance representing the class specification"""
        iri = getattr(model_cls, "_iri_model_name", None)
        if iri is None:
            raise ValueError(f"Model {model_cls.__name__} has no associated IRI.")

        return cls.specify(class_iri=iri, ogm=ogm)

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

        ### Collect special properties
        # Get all types of the class
        triples = db.triples_get(sub=class_iri, pred="rdf:type", include_implicit=True)
        class_types = [triple[2] for triple in triples]
        if not class_types:
            raise ValueError(f"Class {class_iri} has no rdf:type defined.")
        if IRI("owl:Class") not in class_types and IRI("rdfs:Class") not in class_types:
            raise ValueError(f"IRI {class_iri} is not an OWL/RDFS Class.")

        class_spec = cls(
            iri=class_iri,
            types=class_types,
        )

        # Get the (first) label of the class
        label_triples = db.triples_get(
            sub=class_iri, pred="rdfs:label", include_implicit=True
        )
        if label_triples:
            if len(label_triples) > 1:
                logger.warning(
                    f"Class {class_iri} has multiple rdfs:label values; using the first one."
                )
            class_spec.label = str(label_triples[0][2])

        # Get the (first) comment of the class
        comment_triples = db.triples_get(
            sub=class_iri, pred="rdfs:comment", include_implicit=True
        )
        if comment_triples:
            if len(comment_triples) > 1:
                logger.warning(
                    f"Class {class_iri} has multiple rdfs:comment values; using the first one."
                )
            class_spec.comment = str(comment_triples[0][2])

        # Get the superclasses of the class
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

        ### Build property specs of the class
        class_spec.properties = {}

        # inherit properties from superclasses
        for sc in superclasses:
            sc_spec = ClassSpec.specify(class_iri=sc, ogm=ogm)
            duplicated_props = class_spec.properties.keys() & sc_spec.properties.keys()
            if duplicated_props:
                logger.warning(
                    f"Properties {duplicated_props} of {class_iri} are defined in multiple superclasses."
                )
            class_spec.properties.update(sc_spec.properties)

        # own properties override inherited ones
        query = f"""
            PREFIX onto: <http://www.ontotext.com/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT ?property
            FROM onto:explicit
            WHERE {{
                {{
                    ?property rdfs:domain <{class_iri}> .
                }}
                UNION
                {{
                    ?property rdfs:domain ?union_class .
                    ?union_class owl:unionOf ?list .
                    ?list rdf:rest*/rdf:first <{class_iri}> .
                    
                }}
            }}
        """
        query_result = db.query(query, convert_bindings=True)
        properties = (
            b["property"] for b in query_result.get("results", {}).get("bindings", [])
        )

        for prop in properties:
            class_spec.properties[prop] = PropertySpec.specify(prop_iri=prop, ogm=ogm)

        ### Follow property chains to hydrate connected ClassSpecs
        if property_chains:
            for property_chain in property_chains:
                if len(property_chain) == 0:
                    continue  # skip empty chains

                next_property = property_chain[0]
                if next_property not in class_spec.properties:
                    raise ValueError(
                        f"Property {class_spec.iri} -> {next_property} not found while processing property chain."
                    )

                prop_spec = class_spec.properties[next_property]

                if prop_spec.value_kind == PropertyValueKind.COMPLEX:
                    logger.warning(
                        f"Property {class_spec.iri} -> {next_property} of type '{prop_spec.value_kind.name}'."
                        f"This property is always specified, since it poinbts towards a blank node, and therefore could otherwise not be expanded afterwards."
                        
                    )
                    continue

                if prop_spec.nested is None:
                    raise ValueError(
                        f"Property {class_spec.iri} -> {next_property} has no nested ClassSpec (cannot continue property chain)."
                    )

                # Rebuild nested ClassSpec with remaining chain tail
                remaining_chain = property_chain[1:]
                logger.debug(
                    f"'{class_spec.iri}' specifies '{prop_spec.nested.iri}' following chain {[i for i in property_chain]}"
                )
                nested_spec = cls.specify(
                    class_iri=prop_spec.nested.iri,
                    ogm=ogm,
                    property_chains=[remaining_chain] if remaining_chain else None,
                )

                # Replace nested spec for this chain only
                prop_spec.nested = nested_spec

        # Mark as hydrated if it was fully specified
        class_spec._hydrated = True

        return class_spec
