import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SampleCurlSection } from './SampleCurlSection'

function Wrapper({
  children,
  initialSchema,
  serviceAccountIds,
}: Readonly<{ children: ReactNode; initialSchema?: string; serviceAccountIds?: string[] }>) {
  const methods = useForm({
    defaultValues: {
      inputSchema: initialSchema ?? '',
      triggerType: 'webhook_trigger',
      authorizedServiceAccountIds: serviceAccountIds ?? [],
    },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

describe('SampleCurlSection', () => {
  it('renders an expandable section with toggle text', () => {
    render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )

    expect(screen.getByText('Sample request')).toBeInTheDocument()
  })

  it('shows the cURL command when expanded', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )

    await user.click(screen.getByText('Sample request'))

    expect(screen.getByText(/curl -X POST/)).toBeInTheDocument()
    expect(screen.getByText(/example\.com\/webhooks\/test/)).toBeInTheDocument()
  })

  it('includes Content-Type header in the command', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )

    await user.click(screen.getByText('Sample request'))

    expect(screen.getByText(/Content-Type: application\/json/)).toBeInTheDocument()
  })

  it('generates sample body from schema fields', async () => {
    const user = userEvent.setup()
    const schema = JSON.stringify({
      type: 'object',
      properties: { event: { type: 'string' }, count: { type: 'integer' } },
    })

    render(
      <Wrapper initialSchema={schema}>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )

    await user.click(screen.getByText('Sample request'))

    expect(screen.getByText(/example/)).toBeInTheDocument()
  })

  it('escapes single quotes in the URL', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhook's" />
      </Wrapper>
    )

    await user.click(screen.getByText('Sample request'))

    expect(screen.getByText(/curl -X POST/)).toBeInTheDocument()
  })

  it('shows empty JSON body when no schema is defined', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )

    await user.click(screen.getByText('Sample request'))

    expect(screen.getByText(/{}/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Wrapper>
        <SampleCurlSection url="https://example.com/webhooks/test" />
      </Wrapper>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
