import { Alert, Content, ContentVariants, StackItem } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynFormField } from '../../../components/forms/SynFormField'
import { WEBHOOK_BASE_URL } from '../../../utils/backendUrl'

import { PayloadValidationSection } from './PayloadValidationSection'
import { ServiceAccountSelect } from './ServiceAccountSelect'
import { DEFAULT_JSON_SCHEMA, EXAMPLE_JSON_SCHEMA, JSON_SCHEMA_DOWNLOAD_FILENAME } from './triggerFormSchema'
import { useWebhookUrl } from './useWebhookUrl'
import { WebhookPathField } from './WebhookPathField'
import { WebhookUrlPreview } from './WebhookUrlPreview'

const EDA_WEBHOOK_BASE_URL = `${WEBHOOK_BASE_URL}/eda`

export function EdaFields() {
  const fullEdaUrl = useWebhookUrl(EDA_WEBHOOK_BASE_URL)

  return (
    <>
      <StackItem>
        <Alert variant="info" isInline title="EDA activation" component="h4">
          <Content component={ContentVariants.p}>
            This trigger will only take effect once the workflow is published. Copy the endpoint URL into your EDA
            rulebook configuration.
          </Content>
        </Alert>
      </StackItem>

      <WebhookPathField
        fieldId="eda-webhook-path"
        label="Webhook path"
        labelHelp={
          <FieldHelpPopover
            headerContent="Webhook path"
            helpText='Enter a unique name or "slug" to identify this endpoint (e.g., /eda-events). This path helps you identify the trigger in your workflow and will be part of the final generated URL.'
          />
        }
        placeholder="/eda-events"
        helperText="A unique slug for this endpoint (e.g., /eda-events)."
      />

      <WebhookUrlPreview
        url={fullEdaUrl}
        fieldIdPrefix="eda"
        urlLabel={
          <FormLabelWithHelp
            label="Endpoint URL"
            helpText="Your EDA webhook endpoint. Configure your EDA rulebook to send a POST request to this URL. Click the copy icon to capture the full URL."
          />
        }
      />

      <StackItem>
        <SynFormField
          name="authorizedServiceAccountIds"
          label="Authorized service accounts"
          fieldId="eda-authorized-service-accounts"
          labelHelp={
            <FieldHelpPopover
              headerContent="Authorized service accounts"
              helpText="Select the service accounts that are allowed to invoke this EDA trigger endpoint. Callers must authenticate with a Bearer token from one of these service accounts."
            />
          }
        >
          {({ field }) => (
            <ServiceAccountSelect
              id="eda-authorized-service-accounts"
              selectedIds={(field.value ?? []) as string[]}
              onChange={field.onChange}
            />
          )}
        </SynFormField>
      </StackItem>

      <StackItem>
        <PayloadValidationSection
          label={
            <FormLabelWithHelp
              label="Request body"
              helpText="Define the fields expected in incoming events. If incoming data does not match, the trigger will reject the request and the workflow will not run."
            />
          }
          defaultCode={DEFAULT_JSON_SCHEMA}
          exampleCode={EXAMPLE_JSON_SCHEMA}
          modalTitle="Edit JSON schema"
          ariaLabel="JSON schema validation editor"
          downloadFilename={JSON_SCHEMA_DOWNLOAD_FILENAME}
          helperText="Optional JSON Schema for validating incoming EDA payloads."
        />
      </StackItem>
    </>
  )
}
