import { Content, ContentVariants } from '@patternfly/react-core'

import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { toPageTitle } from '../../utils/toPageTitle'

/** Direct-link page that is only loaded when its feature flag route guard passes. */
export function FeatureFlagDemo() {
  return (
    <SynPage>
      <title>{toPageTitle(['Feature flag route demo'])}</title>
      <SynPageHeader title="Feature flag route demo" />
      <SynPageBody>
        <SynPanel isFullHeight>
          <SynPanelContentStack hasGutter>
            <Content component={ContentVariants.p}>
              This direct-link route is guarded by the `workflow_builder_qol` feature flag.
            </Content>
            <Content component={ContentVariants.h2}>Route access granted</Content>
            <Content component={ContentVariants.p}>
              The flag is enabled, so TanStack Router allowed this route to load.
            </Content>
            <Content component={ContentVariants.h3}>Guarded workflow builder preview</Content>
            <Content component={ContentVariants.p}>
              The route checks the flag in TanStack Router&apos;s `beforeLoad` hook and redirects to `/workflows` when
              the flag is off. This is a client-side routing demo, not an access-control boundary.
            </Content>
          </SynPanelContentStack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
