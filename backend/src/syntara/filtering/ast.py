"""Read the native compiler's standard CEL protobuf AST, never parse CEL text."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from google.protobuf import (
    any_pb2,
    descriptor_pb2,
    descriptor_pool,
    duration_pb2,
    empty_pb2,
    json_format,
    message_factory,
    struct_pb2,
    timestamp_pb2,
)
from google.protobuf.message import Message


@lru_cache(maxsize=1)
def _checked_expression_type() -> type[Message]:
    """Load upstream CEL descriptors into a private pool, avoiding global collisions."""
    pool = descriptor_pool.DescriptorPool()
    for module in (duration_pb2, empty_pb2, struct_pb2, timestamp_pb2):
        pool.AddSerializedFile(module.DESCRIPTOR.serialized_pb)
    definitions = descriptor_pb2.FileDescriptorSet.FromString(
        (Path(__file__).parent / "_proto" / "cel.pb").read_bytes()
    )
    for definition in definitions.file:
        pool.Add(definition)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("cel.expr.CheckedExpr"))


class CheckedExpression:
    """Inspect a checked expression and select already-checked subexpressions.

    Dynamic protobuf dictionaries are confined to this native interoperability
    boundary. Source text is neither split nor regenerated for early checks.
    """

    def __init__(self, serialized: bytes) -> None:
        """Read the compiler's Any-wrapped, checked expression."""
        container = any_pb2.Any.FromString(serialized)
        if container.type_url != "type.googleapis.com/cel.expr.CheckedExpr":
            message = "Unsupported native CEL serialization"
            raise ValueError(message)
        checked = _checked_expression_type()()
        checked.ParseFromString(container.value)
        original = checked.SerializeToString(deterministic=True)
        checked.DiscardUnknownFields()
        if checked.SerializeToString(deterministic=True) != original:
            message = "Unsupported native CEL AST fields"
            raise ValueError(message)
        self._checked = json_format.MessageToDict(checked, preserving_proto_field_name=True)
        self.root = self._checked["expr"]

    def subtree(self, expression: dict[str, Any]) -> bytes:
        """Keep compiler type/reference maps when selecting a checked AST node."""
        data = {**self._checked, "expr": expression}
        checked = json_format.ParseDict(data, _checked_expression_type()())
        return any_pb2.Any(
            type_url="type.googleapis.com/cel.expr.CheckedExpr", value=checked.SerializeToString()
        ).SerializeToString()
