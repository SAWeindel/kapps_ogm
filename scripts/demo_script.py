import os
import uvicorn

import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder


def main():
    print("=== Step 1: Initialize GraphDB connection ===")
    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    print(f"✓ Connected to GraphDB repository: {credentials.repository}")

    print("\n=== Step 2: Initialize OGM with minimal builder and loader ===")
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)
    print("✓ OGM initialized with custom builder and loader functions")
    print(f"  - Type cache is empty: {ogm.type_cache}")

    print("\n=== Step 3: Create Node with TransferUnit URI ===")
    node_id = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")
    print(f"Creating node for URI: {node_id}")

    # Create node using OGM - this will trigger the builder
    node_ref = ogm.create_node(id=node_id)
    node = ogm.create_node(id=node_id)
    print(f"✓ Node created: {node}")

    print("\n=== Step 4: Check what happened during node creation ===")
    print(f"  - Node URI: {node.id}")
    print(f"  - Node is loaded: {node.is_loaded}")
    print(f"  - Node model class: {node.model}")
    print(f"  - Type of Node: {type(node)}")
    print(f"  - Type cache now contains: {list(ogm.type_cache.keys())}")
    print(f"  - Cached model class for URI: {ogm.get_type(node_id)}")

    print("\n=== Step 5: Load the node data from GraphDB ===")
    print("Calling node.load() with OGM's loader...")
    loaded_instance = node.load()
    print(f"✓ Node loaded successfully!")
    print(f"  - Loaded instance: {loaded_instance}")
    print(f"  - Instance type: {type(loaded_instance)}")
    print(f"  - Instance URI: {loaded_instance.id}")

    print("\n=== Step 6: Demonstrate type cache reuse ===")
    print("Creating a second node with the same URI...")
    node2 = ogm.create_node(id=node_id)
    print(f"✓ Second node created: {node2}")
    print(f"  - Did it call builder again? No! It reused the cached type.")
    print(f"  - Both nodes share the same model class: {node.model is node2.model}")
    node3 = ogm.create_node(id=node_id, model_cls=node.model)
    print(f"✓ Third node created with both id and model class: {node3}")
    node4 = ogm.create_node(id=node_id, instance=loaded_instance)
    print(f"✓ Fourth node created with both id and instance: {node4}")
    node5 = ogm.create_node(id=node_id, model_cls=node.model, instance=loaded_instance)
    print(f"✓ Fifth node created with id, model class, and instance: {node5}")

    print("\n=== Summary ===")
    print("✓ OGM successfully managed:")
    print("  1. GraphDB connection centralization")
    print("  2. Dynamic model class creation via minimal_builder")
    print("  3. Type caching to avoid rebuilding")
    print("  4. Data loading via minimal_loader")
    print("  5. Node factory with automatic OGM integration")

    data_model = aas.DataModel.from_models(node.instance)
    middleware = aas.AasMiddleware()
    middleware.load_data_model(
        name="TransferUnit_1", data_model=data_model, persist_instances=True
    )
    middleware.generate_rest_api_for_data_model("TransferUnit_1")
    uvicorn.run(middleware.app)


if __name__ == "__main__":
    main()
