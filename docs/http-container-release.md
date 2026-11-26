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
