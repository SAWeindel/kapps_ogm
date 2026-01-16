import json


class OGMEncoder(json.JSONEncoder):
    def default(self, obj):
        from ..node import Node

        if isinstance(obj, Node):
            return obj.data
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)
