# Execution Plane status progression overview

Work delivery status is documented in
[activity binding status progression](activity-binding-status.md).

Integration configuration is committed in AO before best-effort EP delivery.
The Temporal worker's five-minute reconciler retries current desired state. The temporary
EP adapter retains its required internal command counter; physical-ID commands
will remove that compatibility requirement. There is no integration outbox or
asynchronous status field.
