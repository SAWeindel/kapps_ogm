import os
import uvicorn
import logging

import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder
from circular_factory_ogm.loaders.loader_eh import loader_eh

NODE_ID = IRI(
    "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeBInstance"
)


def main():
    # configure root logger to INFO so all module loggers (including loader_eh)
    # will emit INFO+ messages when this script runs
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("circular_factory_ogm")

    logger.debug("=== Step 1: Initialize GraphDB connection ===")
    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    logger.debug(f"✓ Connected to GraphDB repository: {credentials.repository}")
    logger.debug("\n=== Step 2: Initialize OGM with minimal builder and loader ===")
    ogm = OGM(db=db, loader_func=loader_eh, builder_func=minimal_builder)
    logger.debug("✓ OGM initialized with custom builder and loader functions")
    logger.debug(f"  - Type cache is empty: {ogm.type_cache}")

    logger.debug("\n=== Step 3: Create Node with Root Instance URI ===")
    logger.debug(f"Creating node for URI: {NODE_ID}")

    # Create node using OGM - this will trigger the builder
    node_ref = ogm.create_node(id=NODE_ID)
    node = ogm.create_node(id=NODE_ID)
    logger.debug(f"✓ Node created: {node}")

    logger.debug("\n=== Step 4: Check what happened during node creation ===")
    logger.debug(f"  - Node URI: {node.id}")
    logger.debug(f"  - Node is loaded: {node.is_loaded}")
    logger.debug(f"  - Node model class: {node.model}")
    logger.debug(f"  - Type of Node: {type(node)}")
    logger.debug(f"  - Type cache now contains: {list(ogm.type_cache.keys())}")
    logger.debug(f"  - Cached model class for URI: {ogm.get_type(NODE_ID)}")

    node.build()
    ogm.resolve_types()

    logger.debug("\n=== Step 5: Load the node data from GraphDB ===")
    logger.debug("Calling node.load() with OGM's loader...")
    loaded_instance = node.load()
    logger.debug(f"✓ Node loaded successfully!")
    logger.debug(f"  - Loaded instance: {loaded_instance}")
    logger.debug(f"  - Instance type: {type(loaded_instance)}")
    logger.debug(f"  - Instance URI: {loaded_instance.id}")

    logger.debug("\n=== Step 6: Demonstrate type cache reuse ===")
    logger.debug("Creating a second node with the same URI...")
    node2 = ogm.create_node(id=NODE_ID)
    logger.debug(f"✓ Second node created: {node2}")
    logger.debug(f"  - Did it call builder again? No! It reused the cached type.")
    logger.debug(
        f"  - Both nodes share the same model class: {node.model is node2.model}"
    )
    node3 = ogm.create_node(id=NODE_ID, model_cls=node.model)
    logger.debug(f"✓ Third node created with both id and model class: {node3}")
    node4 = ogm.create_node(id=NODE_ID, instance=loaded_instance)
    logger.debug(f"✓ Fourth node created with both id and instance: {node4}")
    node5 = ogm.create_node(id=NODE_ID, model_cls=node.model, instance=loaded_instance)
    logger.debug(f"✓ Fifth node created with id, model class, and instance: {node5}")

    logger.debug("\n=== Summary ===")
    logger.debug("✓ OGM successfully managed:")
    logger.debug("  1. GraphDB connection centralization")
    logger.debug("  2. Dynamic model class creation via minimal_builder")
    logger.debug("  3. Type caching to avoid rebuilding")
    logger.debug("  4. Data loading via minimal_loader")
    logger.debug("  5. Node factory with automatic OGM integration")

    data_model = aas.DataModel.from_models(node.instance)
    middleware = aas.AasMiddleware()
    middleware.load_data_model(
        name="DemoStructure_1", data_model=data_model, persist_instances=True
    )
    middleware.generate_rest_api_for_data_model("DemoStructure_1")
    uvicorn.run(middleware.app)


if __name__ == "__main__":
    main()
