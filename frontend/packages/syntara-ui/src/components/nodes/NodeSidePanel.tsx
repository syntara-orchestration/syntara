import { Stack } from '@patternfly/react-core'

export function NodeSidePanel(props: Readonly<{ children: React.ReactNode }>) {
  return (
    <Stack
      data-testid="node-side-panel"
      hasGutter
      style={{
        padding: 'var(--pf-t--global--spacer--2xl)',
      }}
    >
      {props.children}
    </Stack>
  )
}
