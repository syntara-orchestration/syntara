import { Content, ContentVariants, FlexItem, Title, TitleSizes } from '@patternfly/react-core'

export function NodeTitle(props: { title?: string; subTitle?: string }) {
  return (
    <FlexItem grow={{ default: 'grow' }}>
      <Title
        headingLevel="h2"
        size={TitleSizes.md}
        style={{ marginBottom: 'var(--pf-t--global--spacer--xs)', overflowWrap: 'anywhere' }}
      >
        {props.title || props.subTitle}
      </Title>
      {props.title && props.subTitle && (
        <Content
          component={ContentVariants.small}
          style={{ marginBottom: 'var(--pf-t--global--spacer--sm)', overflowWrap: 'anywhere' }}
        >
          {props.subTitle}
        </Content>
      )}
    </FlexItem>
  )
}
