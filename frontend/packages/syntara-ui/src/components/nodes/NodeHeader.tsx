import { Flex } from '@patternfly/react-core'

export function NodeHeader(props: Readonly<{ children: React.ReactNode }>) {
  return (
    <div
      data-testid="node-header"
      style={{
        paddingTop: 'var(--pf-t--global--spacer--md)',
        paddingLeft: 'var(--pf-t--global--spacer--md)',
        paddingRight: 'var(--pf-t--global--spacer--md)',
      }}
    >
      <Flex
        data-testid="node-header-content"
        alignItems={{ default: 'alignItemsFlexStart' }}
        justifyContent={{ default: 'justifyContentSpaceBetween' }}
      >
        {props.children}
      </Flex>
    </div>
  )
}
