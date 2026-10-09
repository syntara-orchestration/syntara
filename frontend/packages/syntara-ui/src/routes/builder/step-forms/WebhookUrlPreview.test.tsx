import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { WebhookUrlPreview } from './WebhookUrlPreview'

function renderPreview(url = 'https://example.com/api/v1/webhooks/test-path') {
  return render(
    <div>
      <WebhookUrlPreview url={url} urlLabel="Endpoint URL" />
    </div>
  )
}

describe('WebhookUrlPreview', () => {
  it('renders the POST badge', () => {
    renderPreview()
    expect(screen.getByText('POST')).toBeInTheDocument()
  })

  it('renders the webhook URL in a clipboard copy field', () => {
    renderPreview('https://example.com/webhooks/my-hook')
    expect(screen.getByLabelText('Webhook URL')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://example.com/webhooks/my-hook')).toBeInTheDocument()
  })

  it('renders the URL label', () => {
    renderPreview()
    expect(screen.getByText('Endpoint URL')).toBeInTheDocument()
  })

  it('renders with a custom method label', () => {
    render(
      <div>
        <WebhookUrlPreview url="https://example.com" urlLabel="URL" methodLabel="GET" />
      </div>
    )
    expect(screen.getByText('GET')).toBeInTheDocument()
  })

  it('renders with a custom fieldIdPrefix', () => {
    render(
      <div>
        <WebhookUrlPreview url="https://example.com" urlLabel="EDA URL" fieldIdPrefix="eda" />
      </div>
    )
    expect(screen.getByText('POST')).toBeInTheDocument()
    expect(screen.getByText('EDA URL')).toBeInTheDocument()
  })

  it('renders with default methodLabel when not provided', () => {
    render(
      <div>
        <WebhookUrlPreview url="https://example.com/webhooks/test" urlLabel="URL" />
      </div>
    )
    expect(screen.getByText('POST')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://example.com/webhooks/test')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderPreview()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
