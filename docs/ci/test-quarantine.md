# Test quarantine workflow

Flaky tests can be temporarily quarantined via the [syntara-ci repository](https://github.com/syntara-orchestration/syntara-ci).

To request a quarantine, visit that repository, following the `README.md` directions to apply a quarantine and open a pull request. Quarantines can be applied to allow a test to run, but failures will not fail the overall pipeline job for the test case. This can be a useful tool to unblock work for the team as a whole for a known flaky test while a resolution is sought.

Note, that **quarantines should be applied sparingly**! Tests are intended to remain under quarantine temporarily. In the near future, quarantined tests beyond a certain age will be automatically deleted.

## FAQs

### Why are quarantines managed in a separate repository?

Managing quarantines in a separate code repository allows a flaky test to be removed as a blocking check while continuing to allow work to flow in the product repository.

If quarantines are managed in the *same* repository as the target code base, the quarantine becomes a blocker for the entire team, requiring every PR/branch to rebase before merging, creating a bottleneck. In the era of more rapid, agentic development, this represents an unacceptably high tax on velocity.

## Why quarantines and not skips?

Quarantines allow a test to continue to run, allowing data collection on the tests over time. This can allow for a test to organically improve over time, possibly resulting in a quarantine being lifted, even without direct intervention.

For example, an E2E test may become flaky due to a performance regression. As performance in the application is improved elsewhere, the test may become stable and become a candidate for lifting the imposed quarantine.