from graph_db_interface import IRI

FUNDAMENTAL_CONCEPTS = {
    "RDF_TYPE": IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    "RDFS_SUBCLASS_OF": IRI("http://www.w3.org/2000/01/rdf-schema#subClassOf"),
    "OWL_CLASS": IRI("http://www.w3.org/2002/07/owl#Class"),
    "RDFS_CLASS": IRI("http://www.w3.org/2000/01/rdf-schema#Class"),
    "RDFS_DOMAIN": IRI("http://www.w3.org/2000/01/rdf-schema#domain"),
    "RDFS_RANGE": IRI("http://www.w3.org/2000/01/rdf-schema#range"),
    "RDFS_LABEL": IRI("http://www.w3.org/2000/01/rdf-schema#label"),
    "RDFS_DATATYPE": IRI("http://www.w3.org/2000/01/rdf-schema#Datatype"),
    "RDF_TYPE_VALUE": IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
}

PROPERTY_TYPES = {
    IRI("http://www.w3.org/2002/07/owl#ObjectProperty"): "object",
    IRI("http://www.w3.org/2002/07/owl#DatatypeProperty"): "data",
    IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"): "generic",
    IRI("http://www.w3.org/2002/07/owl#AnnotationProperty"): "annotation",
}

PROPERTY_CHARACTERISTICS = {
    IRI("http://www.w3.org/2002/07/owl#FunctionalProperty"): "functional",
    IRI(
        "http://www.w3.org/2002/07/owl#InverseFunctionalProperty"
    ): "inverse_functional",
    IRI("http://www.w3.org/2002/07/owl#TransitiveProperty"): "transitive",
    IRI("http://www.w3.org/2002/07/owl#SymmetricProperty"): "symmetric",
    IRI("http://www.w3.org/2002/07/owl#AsymmetricProperty"): "asymmetric",
    IRI("http://www.w3.org/2002/07/owl#ReflexiveProperty"): "reflexive",
    IRI("http://www.w3.org/2002/07/owl#IrreflexiveProperty"): "irreflexive",
}
