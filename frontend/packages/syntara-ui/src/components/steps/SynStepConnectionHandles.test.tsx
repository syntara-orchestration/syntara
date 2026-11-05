import { render, screen } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX } from '../../routes/workflows/canvas/semanticZoom'

import { SynStepConnectionHandles } from './SynStepConnectionHandles'

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    Handle: (props: { id: string; type: string; style?: React.CSSProperties; position: string }) => (
      <div
        data-testid={`handle-${props.id}`}
        data-handle-type={props.type}
        data-handle-pos={props.position}
        style={props.style}
      />
    ),
    Position: actual.Position,
  }
})

function renderHandles(props: ComponentProps<typeof SynStepConnectionHandles>) {
  return render(
    <ReactFlowProvider>
      <SynStepConnectionHandles {...props} />
    </ReactFlowProvider>
  )
}

const semanticZoomTop = SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX

describe('SynStepConnectionHandles', () => {
  it('renders default target and source handles', () => {
    renderHandles({ isSemanticZoom: false, semanticZoomHandleTop: semanticZoomTop })
    expect(screen.getByTestId('handle-target')).toBeInTheDocument()
    expect(screen.getByTestId('handle-source')).toBeInTheDocument()
  })

  it('omits handles when disabled', () => {
    renderHandles({
      isSemanticZoom: false,
      semanticZoomHandleTop: semanticZoomTop,
      disableTarget: true,
      disableSource: true,
    })
    expect(screen.queryByTestId('handle-target')).not.toBeInTheDocument()
    expect(screen.queryByTestId('handle-source')).not.toBeInTheDocument()
  })

  it('renders optional start and end handles', () => {
    renderHandles({
      isSemanticZoom: false,
      semanticZoomHandleTop: semanticZoomTop,
      enableStart: true,
      enableEnd: true,
    })
    expect(screen.getByTestId('handle-start')).toBeInTheDocument()
    expect(screen.getByTestId('handle-end')).toBeInTheDocument()
  })

  it('swaps handle sides when reverseHandles is set', () => {
    renderHandles({ isSemanticZoom: false, semanticZoomHandleTop: semanticZoomTop, reverseHandles: true })
    expect(screen.getByTestId('handle-target')).toHaveAttribute('data-handle-pos', 'right')
    expect(screen.getByTestId('handle-source')).toHaveAttribute('data-handle-pos', 'left')
  })

  it('applies semantic zoom edge transforms on connection handles', () => {
    renderHandles({
      isSemanticZoom: true,
      semanticZoomHandleTop: semanticZoomTop,
    })
    expect(screen.getByTestId('handle-target')).toHaveStyle({
      top: `${SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX}px`,
      transform: 'translate(-50%, -50%)',
    })
    expect(screen.getByTestId('handle-source')).toHaveStyle({
      top: `${SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX}px`,
      transform: 'translate(50%, -50%)',
    })
  })
})
