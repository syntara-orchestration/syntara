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

Seeding does not switch workflow HTTP requests to the Execution Plane. The
existing HTTP executor remains in use. Runtime migration needs separate handling
for execution targets, credentials and trusted HTTP endpoint context, private-host
policy, and workflow completion/retry/cancellation. Installing the bearer recipe
does not create an HTTP integration instance or enable credentialed dispatch.

Release integration also requires the operator to forward the HTTP image from
its bundle into the backend migration job. The release must supply the signed
image, approved digest and public verification key; this change supplies no
placeholder digest or mutable tag.
