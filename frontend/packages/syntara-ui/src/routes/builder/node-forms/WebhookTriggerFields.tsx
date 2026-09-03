import {
  Alert,
  Content,
  ContentVariants,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  StackItem,
} from '@patternfly/react-core'
import { Controller, useFormContext } from 'react-hook-form'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { WEBHOOK_BASE_URL } from '../../../utils/backendUrl'

import { PayloadValidationSection } from './PayloadValidationSection'
import { SampleCurlSection } from './SampleCurlSection'
import { ServiceAccountSelect } from './ServiceAccountSelect'
import type { TriggerFormData } from './triggerFormSchema'
import { DEFAULT_JSON_SCHEMA, EXAMPLE_JSON_SCHEMA, JSON_SCHEMA_DOWNLOAD_FILENAME } from './triggerFormSchema'
import { useWebhookUrl } from './useWebhookUrl'
import { WebhookPathField } from './WebhookPathField'
import { WebhookUrlPreview } from './WebhookUrlPreview'

export function WebhookFields({
  errors,
}: Readonly<{
  errors: Readonly<{
    webhookPath?: { message?: string }
    inputSchema?: { message?: string }
    authorizedServiceAccountIds?: { message?: string }
  }>
}>) {
  const fullWebhookUrl = useWebhookUrl(WEBHOOK_BASE_URL)
  const { control } = useFormContext<TriggerFormData>()

  return (
    <>
      <StackItem>
        <Alert variant="info" isInline title="Webhook activation" component="h4">
          <Content component={ContentVariants.p}>
            This webhook will only take effect once the workflow is published. Changes to the webhook are applied on the
            next publish.
          </Content>
        </Alert>
      </StackItem>

      <WebhookPathField
        label="Webhook path"
        labelHelp={
          <FieldHelpPopover
            headerContent="Webhook path"
            helpText='Enter a unique name or "slug" to identify this endpoint (e.g., /jira-updates). This path helps you identify the trigger in your workflow and will be part of the final generated URL.'
          />
        }
        placeholder="/jira-updates"
        helperText="A unique slug for this endpoint (e.g., /jira-updates)."
        error={errors.webhookPath?.message}
      />

      <WebhookUrlPreview
        url={fullWebhookUrl}
        urlLabel={
          <FormLabelWithHelp
            label="Endpoint URL"
            helpText="Your webhook endpoint. External services should send a POST request to this URL. Click the copy icon to capture the full URL."
          />
        }
      />

      <StackItem>
        <FormGroup
          label={
            <FormLabelWithHelp
              label="Authorized service accounts"
              helpText="Select the service accounts that are allowed to invoke this webhook trigger endpoint. Callers must authenticate with a Bearer token from one of these service accounts."
            />
          }
          fieldId="webhook-authorized-service-accounts"
        >
          <Controller
            control={control}
            name="authorizedServiceAccountIds"
            render={({ field }) => (
              <ServiceAccountSelect
                id="webhook-authorized-service-accounts"
                selectedIds={field.value ?? []}
                onChange={field.onChange}
              />
            )}
          />
          {errors.authorizedServiceAccountIds?.message && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{errors.authorizedServiceAccountIds.message}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      </StackItem>

      <StackItem>
        <PayloadValidationSection
          label={
            <FormLabelWithHelp
              label="Request body"
              helpText="Define the fields expected in incoming requests. If incoming data does not match, the trigger will reject the request and the workflow will not run."
            />
          }
          defaultCode={DEFAULT_JSON_SCHEMA}
          exampleCode={EXAMPLE_JSON_SCHEMA}
          modalTitle="Edit JSON schema"
          ariaLabel="JSON schema validation editor"
          downloadFilename={JSON_SCHEMA_DOWNLOAD_FILENAME}
          helperText="Optional JSON Schema for validating incoming webhook payloads."
          error={errors.inputSchema?.message}
        />
      </StackItem>

      <SampleCurlSection url={fullWebhookUrl} />
    </>
  )
}
