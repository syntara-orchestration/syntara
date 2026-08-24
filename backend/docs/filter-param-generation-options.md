# Filter Param Spec Generation: Options Considered

## Problem

The `x-spec-only` approach creates divergence between model metadata and the OpenAPI spec. Filter params exist only in hand-authored YAML sub-specs, with nothing validating they match `__filterable_fields__` on the model. The drift checker explicitly ignores these params, which is the opposite of what we want.

## Options

### Option A: Post-process spec at export+bundle time

Inject filter params into the spec dict after FastAPI generates it. Both `export_openapi.py` and `bundle_openapi.py` call a shared `inject_filter_params()` function that reads `__filterable_fields__` + field types from models.

**Pros:**
- Single source of truth (model metadata)
- Sub-specs stay fully hand-authored
- No x-spec-only, no drift checker carve-outs

**Cons:**
- Two scripts need injection logic (export + bundle)
- `bundle_openapi.py` gains a new dependency on model imports (currently YAML-only, but already imports `syntara.api.constants`)
- Sub-specs become an incomplete picture of the API (no filter params visible in YAML)

**Why not chosen:** Sub-specs losing filter params makes them harder to read, and the injection adds complexity to two separate scripts.

### Option B: Generate filter params into sub-spec files

A `make gen-filter-params` step writes filter param blocks into sub-spec YAML from model metadata. Sub-specs become partially generated.

**Pros:**
- Sub-specs show the complete API surface
- Drift checker works naturally (both sides have filter params)
- Single source of truth

**Cons:**
- Sub-specs become partially generated (new pattern — nothing else generates into sub-specs today)
- Needs marker comments to separate generated vs hand-authored sections
- Potential merge conflicts on generated sections

**Why not chosen:** Introducing partially-generated sub-specs muddies the hand-authored contract and adds a new maintenance pattern.

### Option C (original): Keep filter params as Pydantic fields on ListParams

Restore filter params as explicit fields on the ListParams models so FastAPI includes them in the spec natively.

**Pros:**
- Simplest approach — FastAPI just handles it
- No injection, no generation, no post-processing

**Cons:**
- Bracket notation (`name[contains]=value`) doesn't map cleanly to Pydantic model fields
- Each filterable field has multiple operator variants, making the models verbose
- Duplicates information from `__filterable_fields__`

**Why not chosen (as-is):** Evolved into the chosen approach (FilterableModel dependency factory).

### Option D (chosen): FilterableModel dependency factory + hand-authored sub-specs

A `FilterableModel(Credential)` dependency on each list route dynamically generates Pydantic query params from `__filterable_fields__` + model field type introspection. FastAPI generates the correct OpenAPI schema natively. Sub-specs keep their hand-authored filter params (just remove the `x-spec-only` marker). The drift checker validates that sub-spec filter params match what the dependency generates.

**Pros:**
- Single source of truth for validation (model metadata via dependency)
- Sub-specs stay fully hand-authored and show the complete API picture
- No changes to `bundle_openapi.py` or `export_openapi.py`
- Drift checker goes from "ignore filter params" to "validate filter params"
- Follows existing `Depends()` pattern (same as `PermissionChecker`)
- Future path: dependency could return parsed filters, replacing manual `parse_filters()` call
- No x-spec-only, no drift checker carve-outs

**Cons:**
- Adding a filterable field requires updating the sub-spec (but drift checker catches omissions)
- FastAPI cannot generate deepObject-style params natively (see deepObject spike below), so `export_openapi.py` needs a small injection step

**Why chosen:** Least plumbing, most aligned with FastAPI patterns, sub-specs stay readable, and CI enforces consistency. The drift checker becomes the validation mechanism rather than being bypassed.

## deepObject Spike Results

During implementation we investigated whether FastAPI can natively generate `deepObject`-style query params (the format used in hand-authored sub-specs). Results:

### What the sub-specs use

Each filter field is a single `deepObject` query param with an `allOf` schema containing operator properties:

```yaml
- name: name
  in: query
  style: deepObject
  explode: true
  schema:
    allOf:
      - type: string
      - type: object
        properties:
          eq:
            title: Equals
            type: string
          contains:
            title: Contains
            type: string
```

### Approaches tested with FastAPI 0.141

| Approach | Result |
|----------|--------|
| `Depends(PydanticModel)` with nested model fields | FastAPI treats nested Pydantic models as **request body**, not query params |
| `Query(default=None)` with Pydantic model annotation | FastAPI rejects: "Query parameter must be one of the supported types" |
| Flat `Query()` params with bracket aliases (`name[eq]`) | Works — generates individual `name[eq]`, `name[contains]` params, but format doesn't match sub-spec deepObject style |
| `Depends()` on flat Pydantic model | Works — generates flat query params, but no deepObject grouping |

### Conclusion

FastAPI cannot generate deepObject-style query parameters. The `FilterableModel` dependency instead:
1. Acts as a **marker** on the route (callable, returns None at runtime)
2. Provides a `to_openapi_params()` method that generates deepObject-style param dicts matching the sub-spec format
3. The `export_openapi.py` script walks routes, finds `FilterableModel` dependencies, and injects the generated params into the exported spec (same pattern as `_inject_permission_metadata`)
4. The drift checker's existing `_strip_schema_description` is extended to recursively strip `description` keys from schema trees, so hand-authored descriptions in sub-specs don't cause false-positive drift

This means `parse_filters()` continues to handle bracket notation parsing at runtime — the dependency has no runtime effect beyond being a dependency marker.

## Endpoint-to-Model Discovery

We also considered how the generation step discovers which model each list endpoint filters on:

| Approach | Description | Chosen? |
|----------|-------------|---------|
| Route-level metadata | `FilterableModel(Model)` dependency on each route | Yes |
| Centralized registry | `dict[operation_id, model_class]` in one file | No — another thing to keep in sync |
| Convention-based | Derive from response type name | No — fragile if naming isn't 100% consistent |

## Type Introspection

We considered two approaches for getting field type information:

| Approach | Description | Chosen? |
|----------|-------------|---------|
| Introspect from model fields | Keep `__filterable_fields__` as `list[str]`, derive types from `model.model_fields` annotations at generation time | Yes — DRY, type info stays on the field definition |
| Enrich `__filterable_fields__` | Change to `dict[str, str]` mapping field name to type classification | No — duplicates what field types already tell us, more verbose |
