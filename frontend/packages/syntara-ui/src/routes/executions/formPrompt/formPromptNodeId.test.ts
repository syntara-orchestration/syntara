import {
  canvasNodeIdFromPromptNodeId,
  compareFormPromptIterationKeys,
  findFormPromptForCanvasNode,
  findFormPromptIndexForCanvasNode,
  findFormPromptIndexForLookupKeys,
  formPromptIterationSortKey,
  lookupMapByPromptNodeId,
  matchesPromptNodeId,
  resolveFormPromptLookupKeys,
  resolveFormPromptWaitingStartedAt,
} from './formPromptNodeId'

describe('canvasNodeIdFromPromptNodeId', () => {
  it('strips loop-iteration suffixes like approval ids', () => {
    expect(canvasNodeIdFromPromptNodeId('collect_input_iter_1')).toBe('collect_input')
  })
})

describe('resolveFormPromptLookupKeys', () => {
  it('includes composite activity keys for the canvas node', () => {
    const activityStates = new Map([
      ['collect_input#iter-1', { activityId: 'collect_input#iter-1', status: 'waiting' as const }],
    ])
    const keys = resolveFormPromptLookupKeys('collect_input', activityStates)
    expect(keys).toContain('collect_input#iter-1')
  })
})

describe('findFormPromptIndexForLookupKeys', () => {
  it('finds a prompt using any lookup key', () => {
    const prompts = [
      {
        id: 'fp-1',
        prompt_node_id: 'collect_input',
        status: 'pending' as const,
        temporal_activity_id: 'collect_input_iter_1',
      },
    ]
    expect(findFormPromptIndexForLookupKeys(prompts, ['collect_input#iter-1', 'collect_input'])).toBe(0)
  })
})

describe('resolveFormPromptWaitingStartedAt', () => {
  it('prefers activity waiting startedAt over form prompt created_at', () => {
    const activityStates = new Map([
      [
        'collect_input',
        { activityId: 'collect_input', status: 'waiting' as const, startedAt: '2026-10-01T12:00:00.000Z' },
      ],
    ])
    expect(
      resolveFormPromptWaitingStartedAt(
        {
          prompt_node_id: 'collect_input',
          created_at: '2026-01-01T00:00:00.000Z',
        },
        activityStates
      )
    ).toBe('2026-10-01T12:00:00.000Z')
  })
})

describe('findFormPromptForCanvasNode', () => {
  const prompts = [
    {
      id: 'fp-0',
      prompt_node_id: 'collect_input_iter_0',
      status: 'submitted' as const,
      temporal_activity_id: 'collect_input_iter_0',
    },
    {
      id: 'fp-1',
      prompt_node_id: 'collect_input',
      status: 'pending' as const,
      temporal_activity_id: 'collect_input_iter_1',
    },
  ]

  it('prefers pending prompt for canvas node id', () => {
    expect(findFormPromptForCanvasNode(prompts, 'collect_input')?.id).toBe('fp-1')
  })

  it('finds index for matched prompt', () => {
    expect(findFormPromptIndexForCanvasNode(prompts, 'collect_input')).toBe(1)
  })

  it('matches composite activity keys via temporal_activity_id', () => {
    expect(findFormPromptForCanvasNode(prompts, 'collect_input#iter-1')?.id).toBe('fp-1')
  })
})

describe('matchesPromptNodeId', () => {
  it('matches loop suffix to canvas id', () => {
    expect(matchesPromptNodeId('collect_input_iter_2', 'collect_input')).toBe(true)
  })
})

describe('lookupMapByPromptNodeId', () => {
  it('looks up by canvas id or suffixed id', () => {
    const map = new Map([['collect_input', 'Collect input']])
    expect(lookupMapByPromptNodeId(map, 'collect_input_iter_0')).toBe('Collect input')
  })

  it('returns undefined for empty map key inputs', () => {
    const map = new Map([['collect_input', 'Collect input']])
    expect(lookupMapByPromptNodeId(map, null)).toBeUndefined()
    expect(lookupMapByPromptNodeId(undefined, 'collect_input')).toBeUndefined()
  })
})

describe('formPromptIterationSortKey', () => {
  it('uses loop_iteration_path when present', () => {
    expect(formPromptIterationSortKey({ prompt_node_id: 'n', loop_iteration_path: [2, 0] })).toEqual([2, 0])
  })

  it('parses iteration suffix from prompt_node_id', () => {
    expect(formPromptIterationSortKey({ prompt_node_id: 'collect_input_iter_1_iter_0' })).toEqual([1, 0])
  })
})

describe('compareFormPromptIterationKeys', () => {
  it('orders shorter paths before longer when prefixes match', () => {
    expect(compareFormPromptIterationKeys([1], [1, 0])).toBeLessThan(0)
  })

  it('returns zero for equal keys', () => {
    expect(compareFormPromptIterationKeys([1, 2], [1, 2])).toBe(0)
  })
})

describe('findFormPromptForCanvasNode loop selection', () => {
  it('returns exact suffixed prompt_node_id match when canvas id differs', () => {
    const loopPrompts = [
      {
        id: 'fp-suffixed',
        prompt_node_id: 'collect_input_iter_2',
        status: 'pending' as const,
      },
    ]
    expect(findFormPromptForCanvasNode(loopPrompts, 'collect_input_iter_2')?.id).toBe('fp-suffixed')
  })

  it('picks latest pending iteration among loop siblings', () => {
    const loopPrompts = [
      {
        id: 'fp-0',
        prompt_node_id: 'collect_input',
        status: 'pending' as const,
        loop_iteration_path: [0],
      },
      {
        id: 'fp-1',
        prompt_node_id: 'collect_input',
        status: 'pending' as const,
        loop_iteration_path: [1],
      },
    ]
    expect(findFormPromptForCanvasNode(loopPrompts, 'collect_input')?.id).toBe('fp-1')
    expect(findFormPromptIndexForCanvasNode(loopPrompts, 'collect_input')).toBe(1)
  })
})

describe('resolveFormPromptWaitingStartedAt fallbacks', () => {
  it('falls back to created_at when no waiting activity state exists', () => {
    expect(
      resolveFormPromptWaitingStartedAt(
        { prompt_node_id: 'collect_input', created_at: '2026-01-01T00:00:00.000Z' },
        new Map()
      )
    ).toBe('2026-01-01T00:00:00.000Z')
  })

  it('checks temporal_activity_id lookup keys', () => {
    const activityStates = new Map([
      ['act-loop', { activityId: 'act-loop', status: 'waiting' as const, startedAt: '2026-10-02T00:00:00.000Z' }],
    ])
    expect(
      resolveFormPromptWaitingStartedAt(
        {
          prompt_node_id: 'collect_input',
          temporal_activity_id: 'act-loop',
          created_at: '2026-01-01T00:00:00.000Z',
        },
        activityStates
      )
    ).toBe('2026-10-02T00:00:00.000Z')
  })

  it('returns null when prompt status is not pending', () => {
    const activityStates = new Map([
      [
        'collect_input',
        { activityId: 'collect_input', status: 'waiting' as const, startedAt: '2026-10-02T00:00:00.000Z' },
      ],
    ])
    expect(
      resolveFormPromptWaitingStartedAt(
        { prompt_node_id: 'collect_input', status: 'expired', created_at: '2026-01-01T00:00:00.000Z' },
        activityStates
      )
    ).toBeNull()
  })
})
