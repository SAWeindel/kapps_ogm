import graph_db_interface
import os
from graph_db_interface import GraphDBCredentials, GraphDB, IRI


def main():
    credentials= GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(
        credentials=credentials
    )
    triples = [(IRI("https://example.org/subject1"),
                IRI("https://example.org/predicate1"),
                IRI("https://example.org/object1")),
               (IRI("https://example.org/subject2"),
                IRI("https://example.org/predicate2"),
                IRI("https://example.org/object2"))]
    db.triples_add(triples, named_graph=IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances_generated"))


if __name__ == "__main__":
    main()
