import { RhUiPlayIcon, RhUiPauseIcon } from '@patternfly/react-icons'
import { describe, it, expect, beforeEach } from 'vitest'

import { StepRegistry } from './StepRegistry'
import type { StepTypeDefinition } from './StepRegistry'

// Mock form component for testing
const MockForm = () => null

describe('StepRegistry', () => {
  beforeEach(() => {
    // Clear registry before each test
    StepRegistry.clear()
  })

  describe('register', () => {
    it('should register a step type', () => {
      const definition: StepTypeDefinition = {
        id: 'test-step',
        label: 'Test Step',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      }

      StepRegistry.register(definition)

      const registered = StepRegistry.get('test-step')
      expect(registered).toBeDefined()
      expect(registered?.label).toBe('Test Step')
    })

    it('should allow overwriting an existing step', () => {
      StepRegistry.register({
        id: 'duplicate',
        label: 'First',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'duplicate',
        label: 'Second',
        icon: RhUiPauseIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      const registered = StepRegistry.get('duplicate')
      expect(registered?.label).toBe('Second')
    })

    it('should set default values for optional fields', () => {
      StepRegistry.register({
        id: 'test',
        label: 'Test',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      const registered = StepRegistry.get('test')
      expect(registered?.enabled).toBe(true)
      expect(registered?.order).toBe(100)
    })
  })

  describe('unregister', () => {
    it('should remove a registered step', () => {
      StepRegistry.register({
        id: 'remove-me',
        label: 'Remove',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      expect(StepRegistry.get('remove-me')).toBeDefined()

      const result = StepRegistry.unregister('remove-me')
      expect(result).toBe(true)
      expect(StepRegistry.get('remove-me')).toBeUndefined()
    })

    it('should return false when removing non-existent node', () => {
      const result = StepRegistry.unregister('non-existent')
      expect(result).toBe(false)
    })
  })

  describe('get', () => {
    it('should return undefined for non-existent node', () => {
      const result = StepRegistry.get('non-existent')
      expect(result).toBeUndefined()
    })

    it('should return the correct step type', () => {
      StepRegistry.register({
        id: 'specific',
        label: 'Specific Node',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      const result = StepRegistry.get('specific')
      expect(result?.label).toBe('Specific Node')
    })
  })

  describe('getAll', () => {
    it('should return empty array when no nodes registered', () => {
      const result = StepRegistry.getAll()
      expect(result).toEqual([])
    })

    it('should return all enabled nodes', () => {
      StepRegistry.register({
        id: 'node1',
        label: 'Node 1',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'node2',
        label: 'Node 2',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
        enabled: false,
      })

      const result = StepRegistry.getAll()
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('node1')
    })

    it('should sort nodes by order', () => {
      StepRegistry.register({
        id: 'third',
        label: 'Third',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
        order: 30,
      })

      StepRegistry.register({
        id: 'first',
        label: 'First',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
        order: 10,
      })

      StepRegistry.register({
        id: 'second',
        label: 'Second',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
        order: 20,
      })

      const result = StepRegistry.getAll()
      expect(result[0].id).toBe('first')
      expect(result[1].id).toBe('second')
      expect(result[2].id).toBe('third')
    })
  })

  describe('getByCategory', () => {
    beforeEach(() => {
      StepRegistry.register({
        id: 'trigger1',
        label: 'Trigger 1',
        icon: RhUiPlayIcon,
        category: 'trigger',
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'action1',
        label: 'Action 1',
        icon: RhUiPlayIcon,
        category: 'action',
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'trigger2',
        label: 'Trigger 2',
        icon: RhUiPlayIcon,
        category: 'trigger',
        formComponent: MockForm,
        onSubmit: () => {},
      })
    })

    it('should return nodes in specified category', () => {
      const triggers = StepRegistry.getByCategory('trigger')
      expect(triggers).toHaveLength(2)
      expect(triggers.every((n) => n.category === 'trigger')).toBe(true)
    })

    it('should return empty array for non-existent category', () => {
      const result = StepRegistry.getByCategory('other')
      expect(result).toEqual([])
    })
  })

  describe('search', () => {
    beforeEach(() => {
      StepRegistry.register({
        id: 'api-call',
        label: 'API Call',
        icon: RhUiPlayIcon,
        keywords: ['http', 'rest', 'request'],
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'python-script',
        label: 'Python Script',
        icon: RhUiPlayIcon,
        keywords: ['python', 'code', 'script'],
        formComponent: MockForm,
        onSubmit: () => {},
      })
    })

    it('should find nodes by label', () => {
      const result = StepRegistry.search('api')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('api-call')
    })

    it('should find nodes by keyword', () => {
      const result = StepRegistry.search('python')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('python-script')
    })

    it('should find nodes by id', () => {
      const result = StepRegistry.search('script')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('python-script')
    })

    it('should be case insensitive', () => {
      const result = StepRegistry.search('API')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('api-call')
    })

    it('should return empty array when no matches', () => {
      const result = StepRegistry.search('nonexistent')
      expect(result).toEqual([])
    })

    it('should return all nodes for empty query', () => {
      const result = StepRegistry.search('')
      expect(result).toHaveLength(2)
    })
  })

  describe('clear', () => {
    it('should remove all registered nodes', () => {
      StepRegistry.register({
        id: 'node1',
        label: 'Node 1',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      StepRegistry.register({
        id: 'node2',
        label: 'Node 2',
        icon: RhUiPlayIcon,
        formComponent: MockForm,
        onSubmit: () => {},
      })

      expect(StepRegistry.getAll()).toHaveLength(2)

      StepRegistry.clear()

      expect(StepRegistry.getAll()).toHaveLength(0)
    })
  })
})
