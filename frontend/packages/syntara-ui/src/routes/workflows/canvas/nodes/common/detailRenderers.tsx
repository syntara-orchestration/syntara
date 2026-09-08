import { SynCodeBlock } from '../../../../../components/details/SynCodeBlock'
import { SynDetail } from '../../../../../components/details/SynDetail'

const nodeCodeBlockProps = { noMaxHeight: true }

/**
 * Renders a condition detail if condition exists
 */
export function renderCondition(condition?: string) {
  if (!condition) return null
  return (
    <SynDetail label="Condition">
      <SynCodeBlock {...nodeCodeBlockProps}>{condition}</SynCodeBlock>
    </SynDetail>
  )
}

/**
 * Renders outputs as key-value pairs if outputs exist
 */
export function renderOutputs(outputs?: Record<string, unknown>) {
  if (!outputs) return null
  return (
    <SynDetail label="Outputs">
      <SynCodeBlock {...nodeCodeBlockProps}>
        {Object.entries(outputs)
          .map(([key, value]) => `${key}: ${String(value)}`)
          .join('\n')}
      </SynCodeBlock>
    </SynDetail>
  )
}

/**
 * Renders inputs as key-value pairs if inputs exist
 */
export function renderInputs(inputs?: Record<string, unknown>) {
  if (!inputs) return null
  return (
    <SynDetail label="Inputs">
      <SynCodeBlock {...nodeCodeBlockProps}>
        {Object.entries(inputs)
          .map(([key, value]) => `${key}: ${String(value)}`)
          .join('\n')}
      </SynCodeBlock>
    </SynDetail>
  )
}

/**
 * Renders full JSON representation of data if show is true
 */
export function renderJson(data: unknown, show?: boolean, label = 'JSON') {
  if (!show || data === undefined || data === null) return null
  const jsonObject = typeof data === 'object' ? data : { value: data }
  return (
    <SynDetail label={label}>
      <SynCodeBlock jsonObject={jsonObject} {...nodeCodeBlockProps} />
    </SynDetail>
  )
}

/**
 * Renders a generic object as JSON
 */
export function renderObject(label: string, data?: Record<string, unknown>) {
  if (!data) return null
  return (
    <SynDetail label={label}>
      <SynCodeBlock jsonObject={data} {...nodeCodeBlockProps} />
    </SynDetail>
  )
}

/**
 * Renders a simple text detail
 */
export function renderText(label: string, text?: string) {
  if (text === undefined || text === null || text === '') return null
  return (
    <SynDetail label={label}>
      <SynCodeBlock {...nodeCodeBlockProps}>{text}</SynCodeBlock>
    </SynDetail>
  )
}
