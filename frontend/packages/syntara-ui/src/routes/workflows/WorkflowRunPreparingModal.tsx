import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Modal,
  ModalBody,
  ModalFooter,
  Spinner,
} from '@patternfly/react-core'

type WorkflowRunPreparingModalProps = Readonly<{
  isOpen: boolean
  onClose: () => void
}>

export function WorkflowRunPreparingModal({ isOpen, onClose }: WorkflowRunPreparingModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small" aria-label="Preparing workflow run">
      <ModalBody>
        <Flex direction={{ default: 'column' }} alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
          <FlexItem>
            <Spinner size="lg" aria-label="Preparing workflow run" />
          </FlexItem>
          <FlexItem>
            <Content component={ContentVariants.p}>Preparing workflow run…</Content>
          </FlexItem>
        </Flex>
      </ModalBody>
      <ModalFooter>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
