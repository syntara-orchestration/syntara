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

The EP path supports public HTTP requests and explicit bearer bindings. Credentialed nodes select an HTTP integration through `integration_id` and supply one `syntara.http.bearer` entry in `credential_bindings`. The reference must equal the integration's selected `management_credential_id`. The integration must be enabled and visible to the execution project, and the credential must be an enabled HTTP Bearer Token in that project.

AO obtains `httpEndpoint` from the stored integration and compares the request's HTTPS origin before submission. EP receives the reference only. The HTTP handler reads the bearer document through the SDK callback, where AO checks the pairing again and returns `{"token": "..."}`. The Temporal dispatch path skips eager secret resolution for EP HTTP using a history patch.

Create the HTTP integration through the integrations API with `integration_type: http`, `configuration: {integration_type: http, base_url: "https://api.example.com"}`, and the selected bearer credential reference. Existing integration API authorization governs this operation. Then use these node parameters, substituting real IDs:

```json
{
  "method": "GET",
  "url": "https://api.example.com/status",
  "integration_id": "<integration UUID>",
  "credential_bindings": [
    {
      "credential_recipe_id": "syntara.http.bearer",
      "credential_ref": "<same credential UUID as the integration>"
    }
  ],
  "execution_profile": {
    "type": "execution_target",
    "execution_target_id": "<target UUID>"
  }
}
```

The first credentialed contract requires explicit bindings and HTTPS with system certificate verification. Header and query values must be strings. Full outputs are required. The container applies public-destination validation, including redirect checks, and response limits. Standard authentication headers, URL credentials, legacy `credential_id`, and caller-provided secrets are rejected by this dispatch path. Missing seeds, image-policy rejection, and failed submission produce errors.

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
