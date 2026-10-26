These two parser modules are frozen copies from PR 897's pre-Kafka API client
(commit `93f7c9d97a8ac9638f4ccded4ca2e582c51b3c93`). The compatibility test
loads that original parser and enum against actual v1 responses so changes to
the current generated client cannot silently weaken the regression.
