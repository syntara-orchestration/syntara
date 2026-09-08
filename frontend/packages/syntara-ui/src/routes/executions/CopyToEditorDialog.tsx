import {
  Button,
  Content,
  ContentVariants,
  List,
  ListItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Stack,
  StackItem,
} from '@patternfly/react-core'

type CopyToEditorDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  onReplace: () => void
  onFork: () => void
  isForkLoading?: boolean
}>

export function CopyToEditorDialog({
  isOpen,
  onClose,
  onReplace,
  onFork,
  isForkLoading = false,
}: CopyToEditorDialogProps) {
  // 3-button modal (Replace / Fork / Cancel) — SynConfirmationDialog only supports 2 buttons
  return (
    <Modal isOpen={isOpen} onClose={onClose} aria-labelledby="copy-to-editor-title" variant="medium">
      <ModalHeader title="Copy run to editor" labelId="copy-to-editor-title" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component={ContentVariants.p}>
              Copy this specific run of the automation into the editor. This will include:
            </Content>
          </StackItem>
          <StackItem>
            <List>
              <ListItem>
                <strong>The version:</strong> The exact version of the workflow as it existed when the run was made.
              </ListItem>
              <ListItem>
                <strong>The data:</strong> All runtime input variables and output data from each step, pinned as mock
                data.
              </ListItem>
            </List>
          </StackItem>
          <StackItem>
            <Content component={ContentVariants.p}>
              This allows you to troubleshoot exactly where a process failed or reuse the successful data as pinned mock
              data.
            </Content>
          </StackItem>
          <StackItem>
            <Content component={ContentVariants.small}>
              <strong>Note:</strong> &quot;Replace&quot; will overwrite any unsaved changes in the current editor.
            </Content>
          </StackItem>
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button key="replace" variant="primary" onClick={onReplace} isDisabled={isForkLoading}>
          Replace current workflow
        </Button>
        <Button key="fork" variant="secondary" onClick={onFork} isLoading={isForkLoading} isDisabled={isForkLoading}>
          Fork as new workflow
        </Button>
        <Button key="cancel" variant="link" onClick={onClose} isDisabled={isForkLoading}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
