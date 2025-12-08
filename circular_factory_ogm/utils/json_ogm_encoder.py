import json
from circular_factory_ogm.node import Node


class OGMEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Node):
            if obj.is_loaded:
                return {
                    "id": obj.id,
                    "instance": obj.instance.dict(),
                }
            elif obj.model is not None:
                return {
                    "id": obj.id,
                    "model": obj.model.__name__,
                }
            elif obj.data is not None:
                return {
                    "id": obj.id,
                    "data": obj.data,
                }
            else:
                return {
                    "id": obj.id,
                }
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)
