# CEL expression descriptors

`cel/expr/syntax.proto` and `cel/expr/checked.proto` are unmodified upstream
Apache-2.0 definitions from cel-expr/cel-spec tag `v0.24.0`:
https://github.com/cel-expr/cel-spec/tree/v0.24.0/proto/cel/expr
Their copyright and license notices are retained in each file.

These definitions describe the C++ compiler's standard checked AST. They do not
add a parser, interpreter, language extension or runtime dependency.

Regenerate `cel.pb` from this directory with:

```sh
protoc -I . --descriptor_set_out=cel.pb cel/expr/syntax.proto cel/expr/checked.proto
```

The runtime loads the descriptors into a private protobuf pool. Evaluation and
subexpression deserialization both remain in the native C++ CEL engine.
