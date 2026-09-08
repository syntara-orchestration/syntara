import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { type Ref, useState } from 'react'

import { SynSelect } from './SynSelect'

const OPTIONS = ['Apache 2.0', 'GPL-3.0', 'MIT', 'MPL-2.0']

function LicenseSelectToggle({
  toggleRef,
  isOpen,
  selected,
  onToggle,
}: Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isOpen: boolean
  selected: string | undefined
  onToggle: () => void
}>) {
  return (
    <MenuToggle ref={toggleRef} onClick={onToggle} isExpanded={isOpen} isFullWidth isPlaceholder={!selected}>
      {selected ?? 'Select a license'}
    </MenuToggle>
  )
}

function LicenseSelect() {
  const [isOpen, setIsOpen] = useState(false)
  const [selected, setSelected] = useState<string | undefined>()

  return (
    <SynSelect
      isOpen={isOpen}
      selected={selected}
      onSelect={(_event, value) => {
        setSelected(String(value))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef) => (
        <LicenseSelectToggle
          toggleRef={toggleRef}
          isOpen={isOpen}
          selected={selected}
          onToggle={() => setIsOpen((open) => !open)}
        />
      )}
    >
      <SelectList>
        {OPTIONS.map((option) => (
          <SelectOption key={option} value={option}>
            {option}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

const meta: Meta<typeof SynSelect> = {
  component: SynSelect,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'PatternFly Select with Syntara defaults: scrollable menu, `maxMenuHeight` of `min(40vh, 25rem)`, ' +
          'popper `preventOverflow`, scroll containment, and dismiss-on-outer-scroll. Import this instead of ' +
          '`Select` from `@patternfly/react-core`. Keep using PatternFly `MenuToggle`, `SelectList`, and `SelectOption`.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <LicenseSelect />,
}
