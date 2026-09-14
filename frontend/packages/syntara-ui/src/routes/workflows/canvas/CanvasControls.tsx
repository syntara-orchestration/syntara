import { Button, Flex, FlexItem, Icon, Popover } from '@patternfly/react-core'
import {
  RhUiInformationIcon,
  RhUiCaretDownIcon,
  RhUiCaretUpIcon,
  RhUiCleanUpFillIcon,
  RhUiExpandArrowsIcon,
  RhUiZoomInIcon,
  RhUiZoomOutIcon,
} from '@patternfly/react-icons'
import { Panel, useReactFlow } from '@xyflow/react'
import React, { useCallback, useRef, useState } from 'react'

import { SynPanel } from '../../../components/layout/SynPanel'

import { CanvasLegend } from './CanvasLegend'
import { NodeExpandedAllContext } from './nodes/common/NodeExpandedAllContext'

const LEGEND_REGION_ID = 'workflow-canvas-legend'

type CanvasLegendPopoverBodyProps = {
  hide?: () => void
  onClose: () => void
  regionId: string
}

function CanvasLegendPopoverBody({ hide, onClose, regionId }: Readonly<CanvasLegendPopoverBodyProps>) {
  const notifyHide = hide ?? (() => {})
  return <CanvasLegend hide={notifyHide} onClose={onClose} regionId={regionId} />
}

function CanvasLegendPopoverBlock() {
  const [legendOpen, setLegendOpen] = useState(false)
  const legendToggleRef = useRef<HTMLButtonElement>(null)

  const closeLegend = useCallback(() => {
    setLegendOpen(false)
    requestAnimationFrame(() => {
      legendToggleRef.current?.focus()
    })
  }, [])

  const handleLegendShouldClose = useCallback(
    (_event: MouseEvent | KeyboardEvent, hide?: () => void) => {
      hide?.()
      closeLegend()
    },
    [closeLegend]
  )

  const legendPopoverBodyContent = useCallback(
    (hide?: () => void) => {
      if (!legendOpen) return null
      return <CanvasLegendPopoverBody hide={hide} onClose={closeLegend} regionId={LEGEND_REGION_ID} />
    },
    [closeLegend, legendOpen]
  )

  return (
    <FlexItem>
      <Popover
        isVisible={legendOpen}
        position="top-start"
        shouldOpen={() => setLegendOpen(true)}
        shouldClose={handleLegendShouldClose}
        showClose={false}
        hasNoPadding
        hasAutoWidth
        aria-label="Legend"
        bodyContent={legendPopoverBodyContent}
      >
        <Button
          ref={legendToggleRef}
          variant="plain"
          isCircle
          isClicked={legendOpen}
          aria-label={legendOpen ? 'Hide step legend' : 'Show step legend'}
          aria-expanded={legendOpen}
          aria-controls={legendOpen ? LEGEND_REGION_ID : undefined}
          aria-pressed={legendOpen}
          icon={
            <Icon isInline>
              <RhUiInformationIcon />
            </Icon>
          }
        />
      </Popover>
    </FlexItem>
  )
}

export function CanvasControls(
  props: Readonly<{ onLayout: (options?: { markDirty?: boolean }) => void; hideLayout?: boolean }>
) {
  const { fitView, zoomIn, zoomOut } = useReactFlow()
  const { expandAllEvent, collapseAllEvent } = React.use(NodeExpandedAllContext)

  return (
    <Panel position="bottom-left">
      <SynPanel isPill variant="raised" hasNoPadding style={{ padding: 'var(--pf-t--global--spacer--xs)' }}>
        <Flex gap={{ default: 'gapNone' }}>
          <CanvasLegendPopoverBlock />
          <FlexItem>
            <Button
              variant="plain"
              isCircle
              onClick={() => zoomIn()}
              aria-label="Zoom in"
              icon={
                <Icon isInline>
                  <RhUiZoomInIcon />
                </Icon>
              }
            />
          </FlexItem>
          <FlexItem>
            <Button
              variant="plain"
              isCircle
              onClick={() => zoomOut()}
              aria-label="Zoom out"
              icon={
                <Icon isInline>
                  <RhUiZoomOutIcon />
                </Icon>
              }
            />
          </FlexItem>
          <FlexItem>
            <Button
              variant="plain"
              isCircle
              onClick={() => fitView()}
              aria-label="Fit view"
              icon={
                <Icon isInline>
                  <RhUiExpandArrowsIcon />
                </Icon>
              }
            />
          </FlexItem>
          {!props.hideLayout && (
            <>
              <FlexItem>
                <Button
                  variant="plain"
                  isCircle
                  onClick={() => collapseAllEvent.dispatchEvent(new Event('collapseAll'))}
                  aria-label="Collapse all"
                  icon={
                    <Icon isInline>
                      <RhUiCaretUpIcon />
                    </Icon>
                  }
                />
              </FlexItem>
              <FlexItem>
                <Button
                  variant="plain"
                  isCircle
                  onClick={() => expandAllEvent.dispatchEvent(new Event('expandAll'))}
                  aria-label="Expand all"
                  icon={
                    <Icon isInline>
                      <RhUiCaretDownIcon />
                    </Icon>
                  }
                />
              </FlexItem>
              <FlexItem>
                <Button
                  variant="plain"
                  isCircle
                  onClick={() => props.onLayout({ markDirty: true })}
                  aria-label="Reset layout"
                  icon={
                    <Icon isInline>
                      <RhUiCleanUpFillIcon />
                    </Icon>
                  }
                />
              </FlexItem>
            </>
          )}
        </Flex>
      </SynPanel>
    </Panel>
  )
}
