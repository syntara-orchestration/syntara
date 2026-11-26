# HTTP container registry seeding

`RELATED_IMAGE_HTTP_REQUEST` opts the HTTP Action into the existing verified
built-in Action seeder. Set it to the approved repository-qualified image digest
and add `syntara.http-request.http-request` to the image policy configured by
`APP_SCRIPT_IMAGE_POLICY_PATH`. Python and Bash image inputs remain required by
the existing seeder. Without the HTTP image input, HTTP registry assets are not
installed. Without the policy file, built-in Action seeding is skipped.

The packaged Action, HTTP IntegrationType and bearer CredentialRecipe match the
HTTP step container. All configured image references are verified before any
writes. Registry changes commit together; reseeding advances managed image
references while preserving administrator pins.

Seeding alone does not switch workflow HTTP requests to the Execution Plane.
Existing HTTP nodes without an execution profile keep their native executor.
Installing the bearer recipe does not create an HTTP integration instance or
enable credentialed dispatch. See the explicit opt-in contract below.

Release integration also requires the operator to forward the HTTP image from
its bundle into the backend migration job. The release must supply the signed
image, approved digest and public verification key; this change supplies no
placeholder digest or mutable tag.

## Explicit execution-target opt-in

An HTTP node with an `execution_profile` selecting an `execution_target` executes
through the seeded HTTP Action. Nodes without a profile retain the existing HTTP
executor even when the Action is installed. The workflow records a Temporal patch
before adding the execution ID to the HTTP activity, and tracks only opted-in
HTTP activities for EP cancellation.

This initial EP path accepts unauthenticated public HTTP requests with string
header/query values. Credentials (including credential bindings, URL userinfo and
standard authentication headers) are rejected before dispatch. For existing
credentialed or private-host workflows, omit the execution profile. EP HTTP uses
the container's strict public-destination policy and result-size limits; native
private-host exceptions are not forwarded. Missing seeds, rejected image policy
and failed EP submission are errors, with no automatic fallback to another executor.

Execution-target placement and submission/completion use the same shared command
path as script steps. This does not migrate all legacy authentication forms or
promise identical native retry/error behavior. Credentialed EP HTTP still requires
trusted integration-instance context and a separate contract change.

## Live acceptance suite

The HTTP suite is `backend/tests/e2e/execution_plane/test_http_workflow.py`.
It creates temporary workflows and deletes them after each test, cancelling any
unfinished executions first. Successful EP requests must have a claimed/completed
work item with the exact execution UUID and selected target; native requests must
have no corresponding EP work item. Additional cases cover upstream errors,
request timeouts and cancellation. Failure cases disable retries deliberately;
these tests do not establish complete native-versus-EP retry equivalence.

Before running, deploy the HTTP runtime branch and approved seeded image into a
test AO/EP installation. Provide the existing suite inputs: `APP_BASE_URL`,
`APP_ADMIN_PASSWORD_PATH` (or `ADMIN_PASSWORD`), `EP_API_URL`, `EP_API_CA_FILE`,
and `EP_SERVICE_TOKEN` or `EP_AO_JWT_PRIVATE_KEY_FILE`. The JWT material must match
the test deployment. Do not print credentials into logs or put them in workflow
parameters.

HTTP-specific inputs:

- `E2E_HTTP_TARGET_ID`: UUID of a ready EP target in the test deployment.
- `E2E_HTTP_BASE_URL`: operator-owned public HTTPS httpbin-compatible fixture
  supporting `/get`, `/status/503`, `/delay/10` and `/delay/30`. The fixture must
  echo the `marker` query parameter on `/get` and honor the full delays. Both the
  AO worker and selected EP target must reach it. Private cluster addresses are
  unsuitable for the container's current destination policy.
- `E2E_POLL_TIMEOUT`: optional maximum wait per polling phase (defaults to 180s).

From `backend/`, with those inputs set in the local environment:

```sh
uv run pytest tests/e2e/execution_plane/test_http_workflow.py -v
```

Collection, model validation and static checks can run without a cluster. They
are preparation only and must not be reported as live acceptance success.

### Output-selection blocker found during preparation

The shared EP worker filters outputs before storing/sending the result, whereas
AO completion validation currently checks the full Action output schema. A local
reproduction with the packaged HTTP manifest and `{"output": {}}` produces
`ExecutionPlaneProtocolError` because `status_code` is required. The HTTP EP activity therefore rejects any explicit `outputs` selection before
submission, including `outputs: {}`. Use default full outputs or the native
executor until this contract is resolved.
Non-empty mapping expressions also need parity with native output mapping; EP
currently selects keys rather than evaluating those expressions. Resolve this
shared completion/mapping contract before promoting the HTTP runtime draft.
The five initial live cases above use the default full output contract.
