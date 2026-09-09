import { describe, expect, it } from 'vitest'

import type { ApprovalWithDetails } from './Approvals'
import { isApprovalSelectable } from './isApprovalSelectable'

describe('isApprovalSelectable', () => {
  const mockApproval = (status: string): ApprovalWithDetails =>
    ({
      id: '1',
      status,
    }) as ApprovalWithDetails

  it('returns true when all conditions are met', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(true)
  })

  it('returns false when status is not pending', () => {
    const approval = mockApproval('approved')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false when isLoadingPermissions is true', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: true,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false when isCheckingApproverList is true', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: true,
      })
    ).toBe(false)
  })

  it('returns false when canDecideOnThisApproval is false', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: false,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false when canDecideBasedOnApproverList is false', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: false,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false when both permissions are false', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: false,
        canDecideBasedOnApproverList: false,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false when both loading states are true', () => {
    const approval = mockApproval('pending')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: true,
        isCheckingApproverList: true,
      })
    ).toBe(false)
  })

  it('returns false for rejected status', () => {
    const approval = mockApproval('rejected')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })

  it('returns false for timed_out status', () => {
    const approval = mockApproval('timed_out')
    expect(
      isApprovalSelectable({
        approval,
        canDecideOnThisApproval: true,
        canDecideBasedOnApproverList: true,
        isLoadingPermissions: false,
        isCheckingApproverList: false,
      })
    ).toBe(false)
  })
})
