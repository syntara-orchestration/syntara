import { CodeEditorControl } from '@patternfly/react-code-editor'
import { RhUiCopyIcon, RhUiDownloadIcon, RhUiFileCodeIcon, RhUiUndoIcon, RhUiUploadIcon } from '@patternfly/react-icons'
import { memo, useCallback } from 'react'

import { detachPromise } from '../../../utils/detachPromise'

type JsonEditorControlsProps = Readonly<{
  code: string
  onCodeChange: (code: string) => void
  defaultCode: string
  downloadFilename: string
  exampleCode?: string
}>

export const JsonEditorControls = memo(function JsonEditorControls({
  code,
  onCodeChange,
  defaultCode,
  downloadFilename,
  exampleCode,
}: JsonEditorControlsProps) {
  const handleUpload = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) {
        const reader = new FileReader()
        reader.onload = (event) => {
          onCodeChange(event.target?.result as string)
        }
        reader.onerror = () => {
          onCodeChange('')
        }
        reader.readAsText(file)
      }
    }
    input.click()
  }, [onCodeChange])

  const handleCopy = useCallback(() => {
    detachPromise(navigator.clipboard.writeText(code))
  }, [code])

  const handleDownload = useCallback(() => {
    const blob = new Blob([code], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = downloadFilename
    a.click()
    // Defer revoke so the browser has time to initiate the download before the blob URL is freed.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }, [code, downloadFilename])

  const handleReset = useCallback(() => {
    onCodeChange(defaultCode)
  }, [onCodeChange, defaultCode])

  const handleExample = useCallback(() => {
    if (exampleCode) {
      onCodeChange(exampleCode)
    }
  }, [onCodeChange, exampleCode])

  return (
    <>
      {exampleCode && (
        <CodeEditorControl
          icon={<RhUiFileCodeIcon />}
          aria-label="Insert example"
          tooltipProps={{ content: 'Insert example' }}
          onClick={handleExample}
        />
      )}
      <CodeEditorControl
        icon={<RhUiUploadIcon />}
        aria-label="Upload JSON file"
        tooltipProps={{ content: 'Upload JSON file' }}
        onClick={handleUpload}
      />
      <CodeEditorControl
        icon={<RhUiCopyIcon />}
        aria-label="Copy to clipboard"
        tooltipProps={{ content: 'Copy to clipboard' }}
        onClick={handleCopy}
      />
      <CodeEditorControl
        icon={<RhUiDownloadIcon />}
        aria-label="Download as JSON"
        tooltipProps={{ content: 'Download as JSON' }}
        onClick={handleDownload}
      />
      <CodeEditorControl
        icon={<RhUiUndoIcon />}
        aria-label="Reset to default"
        tooltipProps={{ content: 'Reset to default' }}
        onClick={handleReset}
      />
    </>
  )
})
