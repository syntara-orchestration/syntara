import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Spinner,
} from '@patternfly/react-core'
import type { FormsAPI } from '@syntara/contracts'

import { formsClient } from '../../../client'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { DateCell } from '../../../components/table/DateCell'
import { detachPromise } from '../../../utils/detachPromise'

import styles from './FormResponseExpandedDetail.module.css'
import type { FormResponseListRow } from './useFormResponsesData'

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']

function formatResponseData(data: FormPromptRead['response_data']): string {
  if (!data || Object.keys(data).length === 0) {
    return '—'
  }
  return JSON.stringify(data, null, 2)
}

type FormResponseExpandedDetailProps = {
  row: FormResponseListRow
  isExpanded: boolean
}

export function FormResponseExpandedDetail({ row, isExpanded }: Readonly<FormResponseExpandedDetailProps>) {
  const detailQuery = formsClient.useQuery(
    'get',
    '/form_prompts/{form_prompt_id}',
    {
      params: { path: { form_prompt_id: row.id } },
    },
    { enabled: isExpanded }
  )

  if (!isExpanded) {
    return null
  }

  if (detailQuery.isLoading) {
    return <Spinner aria-label="Loading form response details" />
  }

  if (detailQuery.isError) {
    return (
      <SynErrorState
        title="Error loading details"
        message={detailQuery.error}
        onRetry={() => detachPromise(detailQuery.refetch())}
      />
    )
  }

  const detail = detailQuery.data
  const message = detail?.message?.trim() || '—'
  const submittedData = formatResponseData(detail?.response_data)

  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Message</DescriptionListTerm>
        <DescriptionListDescription>{message}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Deadline</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={row.timeout_at ?? detail?.timeout_at ?? null} />
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Submitted data</DescriptionListTerm>
        <DescriptionListDescription>
          <pre className={styles.submittedDataPre}>{submittedData}</pre>
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}
