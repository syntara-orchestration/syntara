import { CodeEditor, CodeEditorControl, Language } from '@patternfly/react-code-editor'
import { Button, Content, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiExternalLinkIcon } from '@patternfly/react-icons'
import type * as monacoEditorCore from 'monaco-editor-core'
import type { KeyboardEvent, Ref } from 'react'
import { useCallback, useImperativeHandle, useState } from 'react'

import { loadShikiService } from '../../../components/details/shiki-service-loader'
import { getShikiTheme } from '../../../components/details/shiki-theme'
import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'
import { useDropTarget } from '../../../hooks/useDropTarget'
import { useMonacoBlur } from '../../../hooks/useMonacoBlur'
import { useColorScheme } from '../../../providers/theme/useColorScheme'
import { detachPromise } from '../../../utils/detachPromise'
import { DROP_TARGET_OUTLINE } from '../panels/utils/dragTypes'

type Monaco = typeof monacoEditorCore

/** Supported code languages for syntax highlighting */
export type CodeLanguage = 'python' | 'bash' | 'json' | 'plaintext'

/** Maps our simple language strings to Monaco's Language enum */
const languageMap: Record<CodeLanguage, Language> = {
  python: Language.python,
  bash: Language.shell,
  json: Language.json,
  plaintext: Language.plaintext,
}

/**
 * Prevents keyboard events from bubbling up to parent components (e.g., ReactFlow)
 * which would otherwise capture keys like Space for canvas panning.
 */
function stopKeyboardPropagation(e: KeyboardEvent) {
  e.stopPropagation()
}

export type ExpandableCodeEditorHandle = {
  getValue: () => string
  /** Focus the editor (e.g. when validation fails and this is the first error field). */
  focus: () => void
  /** Insert text at the current cursor position, or append if no cursor. */
  insertAtCursor: (text: string) => void
}

/**
 * ExpandableCodeEditor component that wraps PatternFly's CodeEditor with an
 * expand button that opens the code in a larger modal window.
 *
 * @example
 * <ExpandableCodeEditor
 *   code={code}
 *   onCodeChange={setCode}
 *   language="python"
 *   height="200px"
 * />
 */
export type ExpandableCodeEditorProps = {
  /** The code content to display/edit */
  code: string
  /** Callback when code changes */
  onCodeChange: (code: string) => void
  /** Programming language for syntax highlighting */
  language?: CodeLanguage
  /** Height of the inline editor (default: "200px") */
  height?: string
  /** Height of the modal editor (default: "500px") */
  modalHeight?: string
  /** Title shown in the modal header */
  modalTitle?: string
  /** Whether the editor is read-only */
  isReadOnly?: boolean
  /** Accessible label for the editor */
  ariaLabel?: string
  /** Whether to show line numbers (default: true) */
  isLineNumbersVisible?: boolean
  /**
   * Override the editor theme (defaults to app's color scheme).
   * Useful for testing or forcing a specific theme regardless of app setting.
   */
  isDarkTheme?: boolean
  /** Called when the editor loses focus (e.g. for blur-based validation). Receives current editor value. */
  onBlur?: (value: string) => void
  /** Called when text is dropped onto the editor (e.g. from an external drag source). */
  onDropText?: (text: string) => void
  /** Extra CodeEditorControl elements rendered in the editor toolbar alongside the expand button. */
  additionalControls?: React.ReactNode
  /** Imperative handle (`getValue` / `focus` / `insertAtCursor`). React 19: `ref` is a regular prop. */
  ref?: Ref<ExpandableCodeEditorHandle>
}

export function ExpandableCodeEditor({
  code,
  onCodeChange,
  language = 'plaintext',
  height = '200px',
  modalHeight = '500px',
  modalTitle = 'Edit script',
  isReadOnly = false,
  ariaLabel = 'Code editor',
  isLineNumbersVisible = true,
  isDarkTheme,
  onBlur,
  onDropText,
  additionalControls,
  ref,
}: ExpandableCodeEditorProps) {
  const { colorScheme } = useColorScheme()

  // Use prop if provided (for testing), otherwise use app theme
  const effectiveTheme = isDarkTheme ?? colorScheme === 'dark'

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [hasShikiMonacoSetup, setHasShikiMonacoSetup] = useState(false)
  useBlurOnOpen(isModalOpen)
  const monacoLanguage = languageMap[language]
  const { getValue, focus, handleEditorDidMount, setValue, editorRef } = useMonacoBlur(code, onBlur)
  const shikiTheme = getShikiTheme(effectiveTheme)
  const patternFlyTheme = effectiveTheme ? 'pf-v6-theme-dark' : 'pf-v6-theme-light'
  const jsonBracketColorizationOptions = language === 'json' ? { bracketPairColorization: { enabled: true } } : {}
  const editorProps = {
    theme: language === 'plaintext' || !hasShikiMonacoSetup ? patternFlyTheme : shikiTheme,
    beforeMount: (monaco: Monaco) => {
      if (language === 'plaintext') return

      detachPromise(
        loadShikiService()
          .then(({ setupMonacoShiki }) => setupMonacoShiki(monaco, shikiTheme))
          .then(() => setHasShikiMonacoSetup(true)),
        { onReject: () => monaco.editor.setTheme(patternFlyTheme) }
      )
    },
  }

  const handleDroppedText = useCallback(
    (text: string) => {
      if (onDropText) {
        onDropText(text)
      }
    },
    [onDropText]
  )

  const { isDropTarget, handleDragOver, handleDragLeave, handleDrop } = useDropTarget({
    onDropText: handleDroppedText,
  })

  useImperativeHandle(ref, () => ({
    getValue,
    focus,
    insertAtCursor: (text: string) => {
      const editor = editorRef.current
      if (!editor) {
        onCodeChange(code + text)
        return
      }
      const selection = editor.getSelection()
      if (selection) {
        editor.executeEdits('drop-insert', [
          {
            range: selection,
            text,
            forceMoveMarkers: true,
          },
        ])
        onCodeChange(editor.getValue())
      }
    },
  }))

  const handleModalClose = () => {
    onBlur?.(getValue())
    setIsModalOpen(false)
  }

  const expandControl = (
    <CodeEditorControl
      icon={<RhUiExternalLinkIcon />}
      aria-label="Open in new window"
      tooltipProps={{ content: 'Open in new window' }}
      onClick={() => setIsModalOpen(true)}
    />
  )

  return (
    <>
      <div
        role="none"
        data-testid="inline-code-editor"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={isDropTarget ? DROP_TARGET_OUTLINE : undefined}
      >
        <CodeEditor
          code={code}
          onCodeChange={(value) => {
            setValue(value)
            onCodeChange(value)
          }}
          onEditorDidMount={handleEditorDidMount}
          onKeyDown={stopKeyboardPropagation}
          language={monacoLanguage}
          height={height}
          isReadOnly={isReadOnly}
          isLineNumbersVisible={isLineNumbersVisible}
          isDarkTheme={effectiveTheme}
          editorProps={editorProps}
          customControls={
            <>
              {additionalControls}
              {expandControl}
            </>
          }
          aria-label={ariaLabel}
          options={{ ariaLabel, ...jsonBracketColorizationOptions }}
        />
      </div>

      <Modal isOpen={isModalOpen} onClose={handleModalClose} variant="large" aria-label={`${modalTitle} modal`}>
        <ModalHeader
          title={modalTitle}
          description={
            <Content component="p">
              Enter or edit the code below. Clicking close will only close this window, the code will still persist in
              the code editor.
            </Content>
          }
        />
        <ModalBody>
          <div data-testid="modal-code-editor">
            <CodeEditor
              code={code}
              onCodeChange={(value) => {
                setValue(value)
                onCodeChange(value)
              }}
              onKeyDown={stopKeyboardPropagation}
              language={monacoLanguage}
              height={modalHeight}
              isReadOnly={isReadOnly}
              isLineNumbersVisible={isLineNumbersVisible}
              isDarkTheme={effectiveTheme}
              editorProps={editorProps}
              aria-label={`${ariaLabel} expanded`}
              options={{ ariaLabel: `${ariaLabel} expanded`, ...jsonBracketColorizationOptions }}
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" onClick={handleModalClose}>
            Close
          </Button>
        </ModalFooter>
      </Modal>
    </>
  )
}
