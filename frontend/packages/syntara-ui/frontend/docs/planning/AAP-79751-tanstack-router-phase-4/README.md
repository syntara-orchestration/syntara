# AAP-79751: Phase 4 TanStack Router Migration Planning

**Jira Ticket**: https://redhat.atlassian.net/browse/AAP-79751
**Created**: 2026-09-21
**Status**: Planning Complete - Awaiting Team Approval

## Overview

This directory contains planning documentation for migrating remaining tabbed pages from the `useUrlTab` pattern to TanStack Router nested layout routes.

## Files

### 📄 `AAP-79751-analysis-summary.md`

Executive summary of the analysis including:

- Ticket discrepancies found
- Actual scope (9 pages vs 5 in ticket)
- Risk assessment
- Success criteria

**Read this first** for a high-level overview.

### 📋 `implementation_plan.md`

Detailed implementation strategy including:

- 6-PR sequence (ordered by complexity)
- Effort estimates per PR
- Risk mitigation strategies
- Testing requirements
- Post-conversion cleanup plan

**Use this** for understanding the rollout approach.

### 🔧 `conversion_example.md`

Technical guide showing:

- Before/after code examples (Group Detail)
- Step-by-step conversion process
- Migration gotchas and solutions
- Test update patterns

**Use this** as a reference when implementing conversions.

## Key Findings

### Scope Correction

The ticket claims User Detail and Credential Detail were converted in Phase 4 - **this is incorrect**. Both still need conversion.

**Actual pages needing conversion**: 9 (not 5)

### Recommended Approach

6 PRs in complexity order:

1. Settings (0.5 day)
2. Access Management Hub (0.75 day)
3. Group + Project Detail (1.5 days)
4. Service Account Detail (0.75 day)
5. Integration + IdP Detail (1.75 days)
6. Credential + User Detail (2 days)

**Total**: ~1.5 weeks

## Next Steps

1. ✅ Analysis complete
2. ✅ Plan documented
3. ✅ Jira comment added
4. ⏳ **Awaiting team feedback** on:
   - Include Service Account + Integration Detail pages?
   - Timeline acceptable?
   - Feature flags needed?
5. ⏳ Implement PR #1 (Settings) once approved

## Notes

- All 9 pages have existing test coverage ✅
- Plan prioritizes low-risk incremental rollout
- `useUrlTab` hook only removed after ALL pages converted
