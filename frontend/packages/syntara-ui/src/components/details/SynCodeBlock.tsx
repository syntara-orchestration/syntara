import {
  Button,
  CodeBlock as PFCodeBlock,
  CodeBlockAction,
  CodeBlockCode,
  ClipboardCopyButton,
  Modal,
  ModalBody,
  ModalHeader,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiExternalLinkIcon } from '@patternfly/react-icons'
import { useId, useState } from 'react'

import { detachPromise } from '../../utils/detachPromise'

import styles from './SynCodeBlock.module.css'

function resolveCopyText(
  codeContent: React.ReactNode,
  jsonObject: object | undefined,
  copyContent: string | undefined
): string {
  if (copyContent) return copyContent
  if (typeof codeContent === 'string') return codeContent
  if (jsonObject) return JSON.stringify(jsonObject, undefined, 2)
  return ''
}

/**
 * Displays code or JSON in execution panels, policy sidebars, and builder views.
 * Commonly used with `enableCopy` and `enableExpand` to let users copy or inspect large payloads in a modal.
 */
export function SynCodeBlock(props: {
  children?: React.ReactNode
  jsonObject?: object
  noMaxHeight?: boolean
  enableCopy?: boolean
  fillHeight?: boolean
  copyContent?: string
  enableExpand?: boolean
  expandTitle?: string
}) {
  const codeContent = props.children ?? (props.jsonObject && JSON.stringify(props.jsonObject, undefined, 2))
  const copyText = resolveCopyText(codeContent, props.jsonObject, props.copyContent)
  const copyButtonId = useId()
  const [isCopied, setIsCopied] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const handleCopy = () => {
    if (!copyText || !navigator.clipboard?.writeText) return
    detachPromise(
      navigator.clipboard
        .writeText(copyText)
        .then(() => {
          setIsCopied(true)
          window.setTimeout(() => setIsCopied(false), 2000)
        })
        .catch(() => {
          // Clipboard denied or unavailable — do not show success state
        })
    )
  }

  const actions = (props.enableCopy || props.enableExpand) && (
    <>
      {props.enableExpand && (
        <CodeBlockAction>
          <Tooltip content="Expand">
            <Button
              variant="plain"
              aria-label="Expand code"
              icon={<RhUiExternalLinkIcon />}
              onClick={() => setIsModalOpen(true)}
            />
          </Tooltip>
        </CodeBlockAction>
      )}
      {props.enableCopy && (
        <CodeBlockAction>
          <ClipboardCopyButton variant="plain" id={copyButtonId} aria-label="Copy to clipboard" onClick={handleCopy}>
            {isCopied ? 'Copied to clipboard' : 'Copy to clipboard'}
          </ClipboardCopyButton>
        </CodeBlockAction>
      )}
    </>
  )

  const modalActions = props.enableCopy && (
    <CodeBlockAction>
      <ClipboardCopyButton
        variant="plain"
        id={`${copyButtonId}-modal`}
        aria-label="Copy to clipboard"
        onClick={handleCopy}
      >
        {isCopied ? 'Copied to clipboard' : 'Copy to clipboard'}
      </ClipboardCopyButton>
    </CodeBlockAction>
  )

  const expandModal = props.enableExpand && (
    <Modal
      isOpen={isModalOpen}
      onClose={() => setIsModalOpen(false)}
      variant="large"
      aria-label={props.expandTitle ?? 'Code detail'}
    >
      <ModalHeader title={props.expandTitle ?? 'Code detail'} />
      <ModalBody>
        <PFCodeBlock actions={modalActions || undefined} className={styles.codeBlock}>
          <CodeBlockCode>{codeContent}</CodeBlockCode>
        </PFCodeBlock>
      </ModalBody>
    </Modal>
  )

  const codeBlock = (
    <PFCodeBlock actions={actions || undefined} className={styles.codeBlock}>
      <CodeBlockCode>{codeContent}</CodeBlockCode>
    </PFCodeBlock>
  )

  if (props.noMaxHeight) {
    return (
      <>
        {codeBlock}
        {expandModal}
      </>
    )
  }

  return (
    <>
      <div
        data-testid="code-block-wrapper"
        style={{
          maxHeight: props.fillHeight ? 'none' : '24rem',
          height: props.fillHeight ? '100%' : undefined,
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {codeBlock}
      </div>
      {expandModal}
    </>
  )
}
