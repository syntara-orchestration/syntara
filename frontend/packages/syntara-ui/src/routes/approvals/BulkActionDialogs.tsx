import { BulkApproveDialog } from './BulkApproveDialog'
import { BulkRejectDialog } from './BulkRejectDialog'

type BulkActionDialogsProps = {
  bulkApproveDialogOpen: boolean
  setBulkApproveDialogOpen: (open: boolean) => void
  bulkRejectDialogOpen: boolean
  setBulkRejectDialogOpen: (open: boolean) => void
  handleBulkApprove: (note: string | null) => void
  handleBulkReject: (note: string | null) => void
  selectedCount: number
  isBulkActionPending: boolean
}

export function BulkActionDialogs({
  bulkApproveDialogOpen,
  setBulkApproveDialogOpen,
  bulkRejectDialogOpen,
  setBulkRejectDialogOpen,
  handleBulkApprove,
  handleBulkReject,
  selectedCount,
  isBulkActionPending,
}: Readonly<BulkActionDialogsProps>) {
  return (
    <>
      <BulkApproveDialog
        isOpen={bulkApproveDialogOpen}
        onClose={() => setBulkApproveDialogOpen(false)}
        onConfirm={handleBulkApprove}
        approvalCount={selectedCount}
        isLoading={isBulkActionPending}
      />

      <BulkRejectDialog
        isOpen={bulkRejectDialogOpen}
        onClose={() => setBulkRejectDialogOpen(false)}
        onConfirm={handleBulkReject}
        approvalCount={selectedCount}
        isLoading={isBulkActionPending}
      />
    </>
  )
}
