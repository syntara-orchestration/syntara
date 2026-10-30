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
import type { ReactNode } from 'react'

import { detachPromise } from '../../utils/detachPromise'

import type { ShikiLanguage, ShikiToken, ShikiTokenLines } from './shiki-service'
import styles from './SynCodeBlock.module.css'
import { useSynCodeHighlight } from './useSynCodeHighlight'
import type { HighlightedCodeView } from './useSynCodeHighlight'

type SearchRange = Readonly<{ start: number; end: number }>

type SynCodeBlockProps = {
  children?: ReactNode
  jsonObject?: object
  noMaxHeight?: boolean
  enableCopy?: boolean
  fillHeight?: boolean
  copyContent?: string
  enableExpand?: boolean
  expandTitle?: string
  /** Applies a Shiki grammar to string content. Supported languages load on demand. */
  language?: ShikiLanguage
  /** Optional ID applied to the code block's pre element. */
  codeId?: string
  /** Stable identity for retaining visible output while the same content is refreshed. */
  highlightKey?: string
  /** Literal, case-insensitive, line-based search term for highlighted string content. */
  searchTerm?: string
}

function resolveCopyText(
  codeContent: ReactNode,
  jsonObject: object | undefined,
  copyContent: string | undefined
): string {
  if (copyContent !== undefined) return copyContent
  if (typeof codeContent === 'string') return codeContent
  if (jsonObject) return JSON.stringify(jsonObject, undefined, 2)
  return ''
}

function resolveCodeContent(props: SynCodeBlockProps): ReactNode {
  return props.children ?? (props.jsonObject && JSON.stringify(props.jsonObject, undefined, 2))
}

function resolveHighlightKey(
  language: ShikiLanguage | undefined,
  source: string | undefined,
  highlightKey?: string
): string {
  if (!language) return ''
  return highlightKey ?? source ?? ''
}

function resolveDisplayedCode(
  shouldHighlight: boolean,
  codeContent: ReactNode,
  highlightedView: HighlightedCodeView,
  searchTerm: string
): ReactNode {
  return shouldHighlight ? renderHighlightedView(highlightedView, searchTerm) : codeContent
}

function resolveCopySource(options: {
  shouldHighlight: boolean
  highlightedView: HighlightedCodeView
  codeContent: ReactNode
  jsonObject: object | undefined
  copyContent: string | undefined
}): string {
  if (options.copyContent !== undefined) return options.copyContent
  if (options.shouldHighlight) return options.highlightedView.source
  return resolveCopyText(options.codeContent, options.jsonObject, undefined)
}

function findSearchRanges(source: string, searchTerm: string): SearchRange[] {
  if (!searchTerm.trim()) return []

  const escapedTerm = searchTerm.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const ranges: SearchRange[] = []
  let lineOffset = 0

  for (const line of source.split('\n')) {
    for (const match of line.matchAll(new RegExp(escapedTerm, 'gi'))) {
      const start = lineOffset + (match.index ?? 0)
      ranges.push({ start, end: start + match[0].length })
    }
    lineOffset += line.length + 1
  }

  return ranges
}

function renderTokenParts(
  token: ShikiToken,
  tokenIndex: number,
  tokenOffset: number,
  ranges: ReadonlyArray<SearchRange>
): ReactNode[] {
  const parts: ReactNode[] = []
  let currentOffset = 0
  const tokenEnd = tokenOffset + token.content.length

  for (const range of ranges) {
    const start = Math.max(range.start, tokenOffset)
    const end = Math.min(range.end, tokenEnd)
    if (start >= end) continue

    const localStart = start - tokenOffset
    const localEnd = end - tokenOffset
    if (currentOffset < localStart) {
      parts.push(
        renderTokenSegment(
          token,
          token.content.slice(currentOffset, localStart),
          `token-${tokenIndex}-part-${parts.length}`,
          false
        )
      )
    }

    parts.push(
      renderTokenSegment(
        token,
        token.content.slice(localStart, localEnd),
        `token-${tokenIndex}-match-${parts.length}`,
        true
      )
    )
    currentOffset = localEnd
  }

  if (currentOffset < token.content.length) {
    parts.push(
      renderTokenSegment(token, token.content.slice(currentOffset), `token-${tokenIndex}-part-${parts.length}`, false)
    )
  }

  return parts
}

function renderTokenSegment(token: ShikiToken, content: string, key: string, isMatch: boolean): ReactNode {
  return (
    <mark
      key={key}
      role={isMatch ? undefined : 'presentation'}
      className={`${styles.syntaxToken}${isMatch ? ` ${styles.searchMark}` : ''}`}
      style={{ ...token.style }}
    >
      {content}
    </mark>
  )
}

function renderTokenStream(tokens: ReadonlyArray<ShikiToken>, source: string, searchTerm: string): ReactNode {
  const ranges = findSearchRanges(source, searchTerm)
  const nodes: ReactNode[] = []
  let tokenOffset = 0

  for (const [tokenIndex, token] of tokens.entries()) {
    nodes.push(...renderTokenParts(token, tokenIndex, tokenOffset, ranges))
    tokenOffset += token.content.length
  }

  return nodes
}

function renderTokenLines(tokenLines: ShikiTokenLines, source: string, searchTerm: string): ReactNode {
  const lineBreakToken: ShikiToken = { content: '\n', style: {} }
  const tokens = tokenLines.flatMap((line, lineIndex) => (lineIndex === 0 ? [...line] : [lineBreakToken, ...line]))
  return renderTokenStream(tokens, source, searchTerm)
}

function renderPlainSource(source: string, searchTerm: string): ReactNode {
  return renderTokenStream([{ content: source, style: {} }], source, searchTerm)
}

function renderHighlightedView(view: HighlightedCodeView, searchTerm: string): ReactNode {
  return view.status === 'ready'
    ? renderTokenLines(view.tokens, view.source, searchTerm)
    : renderPlainSource(view.source, searchTerm)
}

function copyToClipboard(copyText: string, onSuccess: () => void): void {
  if (!copyText || !navigator.clipboard?.writeText) return
  detachPromise(
    navigator.clipboard
      .writeText(copyText)
      .then(onSuccess)
      .catch(() => {
        // Clipboard denied or unavailable — do not show success state
      })
  )
}

function CodeBlockActions(props: {
  copyId: string
  enableCopy: boolean
  enableExpand: boolean
  isCopied: boolean
  onCopy: () => void
  onExpand: () => void
}) {
  return (
    <>
      {props.enableExpand && (
        <CodeBlockAction>
          <Tooltip content="Expand">
            <Button variant="plain" aria-label="Expand code" icon={<RhUiExternalLinkIcon />} onClick={props.onExpand} />
          </Tooltip>
        </CodeBlockAction>
      )}
      {props.enableCopy && <CopyCodeAction copyId={props.copyId} isCopied={props.isCopied} onCopy={props.onCopy} />}
    </>
  )
}

function CopyCodeAction(props: { copyId: string; isCopied: boolean; onCopy: () => void }) {
  return (
    <CodeBlockAction>
      <ClipboardCopyButton variant="plain" id={props.copyId} aria-label="Copy to clipboard" onClick={props.onCopy}>
        {props.isCopied ? 'Copied to clipboard' : 'Copy to clipboard'}
      </ClipboardCopyButton>
    </CodeBlockAction>
  )
}

function CodeDetailModal(props: {
  isOpen: boolean
  title: string
  actions: ReactNode
  code: ReactNode
  onClose: () => void
}): ReactNode {
  return (
    <Modal isOpen={props.isOpen} onClose={props.onClose} variant="large" aria-label={props.title}>
      <ModalHeader title={props.title} />
      <ModalBody>
        <PFCodeBlock actions={props.actions || undefined} className={styles.codeBlock}>
          <CodeBlockCode>{props.code}</CodeBlockCode>
        </PFCodeBlock>
      </ModalBody>
    </Modal>
  )
}

function getCodeBlockActions(options: {
  copyId: string
  enableCopy: boolean
  enableExpand: boolean
  isCopied: boolean
  onCopy: () => void
  onExpand: () => void
}): ReactNode {
  if (!options.enableCopy && !options.enableExpand) return undefined
  return <CodeBlockActions {...options} />
}

function getModalActions(options: {
  copyId: string
  enableCopy: boolean
  isCopied: boolean
  onCopy: () => void
}): ReactNode {
  return options.enableCopy ? <CopyCodeAction {...options} /> : undefined
}

function getExpandModal(options: {
  enabled: boolean
  isOpen: boolean
  title: string
  actions: ReactNode
  code: ReactNode
  onClose: () => void
}): ReactNode {
  if (!options.enabled) return null
  return (
    <CodeDetailModal
      isOpen={options.isOpen}
      title={options.title}
      actions={options.actions}
      code={options.code}
      onClose={options.onClose}
    />
  )
}

/**
 * Displays code or JSON in execution panels, policy sidebars, and builder views.
 * Commonly used with `enableCopy` and `enableExpand` to let users copy or inspect large payloads in a modal.
 */
export function SynCodeBlock(props: SynCodeBlockProps) {
  const codeContent = resolveCodeContent(props)
  const source = typeof codeContent === 'string' ? codeContent : undefined
  const language = source !== undefined ? props.language : undefined
  const highlightKey = resolveHighlightKey(language, source, props.highlightKey)
  const shouldHighlight = Boolean(language && source !== undefined)
  const highlightedView = useSynCodeHighlight(shouldHighlight, source, language, highlightKey)
  const copyButtonId = useId()
  const [isCopied, setIsCopied] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const copyText = resolveCopySource({
    shouldHighlight,
    highlightedView,
    codeContent,
    jsonObject: props.jsonObject,
    copyContent: props.copyContent,
  })
  const searchTerm = props.searchTerm ?? ''
  const displayedCode = resolveDisplayedCode(shouldHighlight, codeContent, highlightedView, searchTerm)

  const handleCopy = () => {
    copyToClipboard(copyText, () => {
      setIsCopied(true)
      window.setTimeout(() => setIsCopied(false), 2000)
    })
  }

  const onExpand = () => setIsModalOpen(true)
  const actions = getCodeBlockActions({
    copyId: copyButtonId,
    enableCopy: Boolean(props.enableCopy),
    enableExpand: Boolean(props.enableExpand),
    isCopied,
    onCopy: handleCopy,
    onExpand,
  })
  const modalActions = getModalActions({
    copyId: `${copyButtonId}-modal`,
    enableCopy: Boolean(props.enableCopy),
    isCopied,
    onCopy: handleCopy,
  })
  const expandModal = getExpandModal({
    enabled: Boolean(props.enableExpand),
    isOpen: isModalOpen,
    title: props.expandTitle ?? 'Code detail',
    actions: modalActions,
    code: displayedCode,
    onClose: () => setIsModalOpen(false),
  })

  const codeBlock = (
    <PFCodeBlock actions={actions} className={styles.codeBlock}>
      <CodeBlockCode id={props.codeId}>{displayedCode}</CodeBlockCode>
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
