# Test quarantine workflow

Flaky tests can be temporarily quarantined via the [syntara-ci repository](https://github.com/syntara-orchestration/syntara-ci). A quarantine keeps the test running while preventing a known failure from blocking the pipeline. Use this only as a temporary measure while the underlying problem is investigated.

## Requesting a quarantine

1. In the [syntara-ci repository](https://github.com/syntara-orchestration/syntara-ci), choose the file for the affected suite:
   - [`backend.md`](https://github.com/syntara-orchestration/syntara-ci/blob/main/backend.md) for backend pytest tests.
   - [`playwright.md`](https://github.com/syntara-orchestration/syntara-ci/blob/main/playwright.md) for frontend Playwright tests.
2. Add an H1 heading containing the complete test identifier, followed by a short explanation of the failure and why it is believed to be flaky.
   - Backend identifiers use the full pytest node ID, such as `tests/e2e/workflows/test_wait_node.py::test_wait_node_zero_duration_fails`.
   - Playwright identifiers use `file.spec.ts > Describe block > test name`.
3. Open a pull request against `syntara-ci` and include a link to the failing check or other supporting evidence.

The quarantine list is consumed by CI automatically. Quarantined tests continue to run and their results remain available for investigating the failure.

Note that **quarantines should be applied sparingly**! Tests are intended to remain under quarantine temporarily. In the near future, quarantined tests beyond a certain age will be automatically deleted.

## FAQs

### Why are quarantines managed in a separate repository?

Managing quarantines in a separate code repository allows a flaky test to be removed as a blocking check while allowing work to continue in the product repository.

If quarantines are managed in the *same* repository as the target code base, the quarantine becomes a blocker for the entire team, requiring every PR/branch to rebase before merging, creating a bottleneck. In the era of more rapid, agentic development, this represents an unacceptably high tax on velocity.

### Why quarantines and not skips?

Quarantines allow a test to continue running, enabling data collection over time. This can allow a test to improve organically, possibly resulting in the quarantine being lifted even without direct intervention.

For example, an E2E test may become flaky due to a performance regression. As the application's performance improves elsewhere, the test may become stable and a candidate for lifting the imposed quarantine.
