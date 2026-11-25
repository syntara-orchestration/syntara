import {
  Button,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  Icon,
  SearchInput,
  Stack,
  StackItem,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiCompressArrowsIcon, RhUiExpandArrowsIcon } from '@patternfly/react-icons'
import { useEffect, useMemo, useRef, useState } from 'react'

import { SynCodeBlock } from '../../components/details/SynCodeBlock'
import { highlightTextLines } from '../../utils/highlightText'
import { InputSchemaView } from '../builder/panels/views/InputSchemaView'
import { InputTableView } from '../builder/panels/views/InputTableView'
import { ViewToggle, type PanelView } from '../builder/panels/ViewToggle'

import styles from './StepExecutionDetailsPanel.module.css'

export type IoPaneLayout = 'split' | 'parameters' | 'output'

const PANE_LAYOUT_ACTION_LABELS = {
  parameters: {
    expand: 'Expand parameters panel',
    restore: 'Restore parameters panel layout',
  },
  output: {
    expand: 'Expand output panel',
    restore: 'Restore output panel layout',
  },
} as const

function NoDataState({ label }: Readonly<{ label: string }>) {
  return (
    <EmptyState headingLevel="h3" titleText={`No ${label} data`} variant="xs">
      <EmptyStateBody>No {label} data is available for this activity.</EmptyStateBody>
    </EmptyState>
  )
}

type DataPaneProps = {
  title: string
  stepId: string
  data: Record<string, unknown> | null
  view: PanelView
  onViewChange: (view: PanelView) => void
  isErrorState?: boolean
  paneKey: 'parameters' | 'output'
  paneLayout: IoPaneLayout
  onPaneLayoutChange: (layout: IoPaneLayout) => void
}

export function StepExecutionDetailsDataPane({
  title,
  stepId,
  data,
  view,
  onViewChange,
  isErrorState = false,
  paneKey,
  paneLayout,
  onPaneLayoutChange,
}: Readonly<DataPaneProps>) {
  const [searchTerm, setSearchTerm] = useState('')
  const [layoutTooltipOpen, setLayoutTooltipOpen] = useState(false)
  const [layoutTooltipContent, setLayoutTooltipContent] = useState('')
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const jsonText = useMemo(() => (data ? JSON.stringify(data, null, 2) : ''), [data])

  const highlightedJson = useMemo(() => {
    if (!jsonText) return undefined
    return highlightTextLines(jsonText, searchTerm)
  }, [jsonText, searchTerm])

  useEffect(() => {
    if (searchTerm && scrollContainerRef.current) {
      requestAnimationFrame(() => {
        const firstMark = scrollContainerRef.current?.querySelector('mark')
        if (firstMark && typeof firstMark.scrollIntoView === 'function') {
          firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      })
    }
  }, [searchTerm, view, highlightedJson])

  function renderContent() {
    if (!data) {
      return <NoDataState label={title.toLowerCase()} />
    }
    switch (view) {
      case 'schema':
        return <InputSchemaView data={data} nodeId={stepId} searchTerm={searchTerm} />
      case 'table':
        return <InputTableView data={data} searchTerm={searchTerm} />
      case 'json':
        return (
          <div style={isErrorState ? { color: 'var(--pf-t--global--color--status--danger--default)' } : undefined}>
            <SynCodeBlock enableCopy enableExpand expandTitle={`${title} JSON`} noMaxHeight copyContent={jsonText}>
              {highlightedJson ?? jsonText}
            </SynCodeBlock>
          </div>
        )
    }
  }

  const isPaneExpanded = paneLayout === paneKey
  const paneLayoutActionLabel = isPaneExpanded
    ? PANE_LAYOUT_ACTION_LABELS[paneKey].restore
    : PANE_LAYOUT_ACTION_LABELS[paneKey].expand
  const PaneLayoutIcon = isPaneExpanded ? RhUiCompressArrowsIcon : RhUiExpandArrowsIcon

  function openLayoutTooltip() {
    setLayoutTooltipContent(paneLayoutActionLabel)
    setLayoutTooltipOpen(true)
  }

  function closeLayoutTooltip() {
    setLayoutTooltipOpen(false)
  }

  function handlePaneLayoutClick() {
    closeLayoutTooltip()
    onPaneLayoutChange(isPaneExpanded ? 'split' : paneKey)
  }

  const searchAndViewControls = (
    <Flex
      alignItems={{ default: 'alignItemsCenter' }}
      gap={{ default: 'gapSm' }}
      flexWrap={{ default: 'wrap' }}
      className={styles.dataPaneControlsStacked}
    >
      <FlexItem grow={{ default: 'grow' }} className={styles.searchWrap}>
        <SearchInput
          aria-label={`Search ${title.toLowerCase()} data`}
          placeholder="Search"
          value={searchTerm}
          onChange={(_event, value) => setSearchTerm(value)}
          onClear={() => setSearchTerm('')}
        />
      </FlexItem>
      <FlexItem grow={{ default: 'grow' }}>
        <ViewToggle activeView={view} onChange={onViewChange} ariaLabel={`${title} view selection`} />
      </FlexItem>
    </Flex>
  )

  return (
    <Stack className={styles.contentContainer}>
      <StackItem className={styles.dataPaneHeaderRow}>
        <div className={styles.dataPaneHeader}>
          <Flex
            className={styles.dataPaneTitleRow}
            justifyContent={{ default: 'justifyContentSpaceBetween' }}
            alignItems={{ default: 'alignItemsCenter' }}
          >
            <FlexItem className={styles.dataPaneTitle}>{title}</FlexItem>
            <FlexItem>
              <Tooltip content={layoutTooltipContent} trigger="manual" isVisible={layoutTooltipOpen}>
                <Button
                  variant="plain"
                  aria-label={paneLayoutActionLabel}
                  aria-pressed={isPaneExpanded}
                  onMouseEnter={openLayoutTooltip}
                  onMouseLeave={closeLayoutTooltip}
                  onFocus={openLayoutTooltip}
                  onBlur={closeLayoutTooltip}
                  onPointerDown={closeLayoutTooltip}
                  onClick={handlePaneLayoutClick}
                  icon={
                    <Icon isInline>
                      <PaneLayoutIcon />
                    </Icon>
                  }
                />
              </Tooltip>
            </FlexItem>
          </Flex>
          {searchAndViewControls}
        </div>
      </StackItem>
      <StackItem isFilled className={styles.scrollPane}>
        <div ref={scrollContainerRef}>{renderContent()}</div>
      </StackItem>
    </Stack>
  )
}
