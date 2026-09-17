import { Button, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'

import { SynCodeBlock } from '../../components/details/SynCodeBlock'
import { useBlurOnOpen } from '../../hooks/useBlurOnOpen'

import { buildPolicyDefinitionJson } from './policyUtils'
import type { PolicyRead } from './types'

export type PolicyJsonModalProps = {
  isOpen: boolean
  policy: PolicyRead
  onClose: () => void
}

export function PolicyJsonModal({ isOpen, policy, onClose }: Readonly<PolicyJsonModalProps>) {
  useBlurOnOpen(isOpen)
  // Only name, description, and statements are the policy definition; scope/type/ids appear in sidebar details.
  const policyJson = buildPolicyDefinitionJson(policy)

  const title = `${policy.name} policy definition`

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="large"
      aria-labelledby={`policy-json-modal-title-${policy.id}`}
      aria-describedby="policy-json-modal-body"
    >
      <ModalHeader title={title} labelId={`policy-json-modal-title-${policy.id}`} />
      <ModalBody id="policy-json-modal-body">
        <SynCodeBlock jsonObject={policyJson} noMaxHeight enableCopy />
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose} aria-label="Close policy definition">
          Close
        </Button>
      </ModalFooter>
    </Modal>
  )
}
