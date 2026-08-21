import {
  Content,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  SearchInput,
} from '@patternfly/react-core'
import { useMemo } from 'react'

import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { NxEmptyStateFilter } from '../../../components/states/NxEmptyStateFilter'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useFuse } from '../../../hooks/useFuse'

import { useGlossaryTerms } from './useGlossaryTerms'

const GLOSSARY_SEARCH_KEYS = [
  { name: 'term' as const, weight: 0.7 },
  { name: 'definition' as const, weight: 0.3 },
]

export default function Glossary() {
  const glossaryTerms = useGlossaryTerms()
  const memoizedTerms = useMemo(() => [...glossaryTerms], [glossaryTerms])
  const { search, setSearch, items: results } = useFuse(memoizedTerms, GLOSSARY_SEARCH_KEYS)

  return (
    <SynPage>
      <SynPageTitle segments={['Glossary']} />
      <SynPageHeader
        title="Glossary"
        toolbar={
          <SearchInput
            placeholder="Search glossary..."
            value={search}
            onChange={(_event, value) => setSearch(value)}
            onClear={() => setSearch('')}
            style={{ width: '16rem' }}
          />
        }
      />
      {results.length === 0 ? (
        <SynPageBody>
          <SynPanel isFullHeight>
            <NxEmptyStateFilter clearAllFilters={() => setSearch('')} />
          </SynPanel>
        </SynPageBody>
      ) : (
        <SynPageBody>
          <SynPanel isFullHeight isScrollable>
            <DescriptionList>
              {results.map((result) => (
                <DescriptionListGroup key={result.term}>
                  <DescriptionListTerm>
                    <Content>{result.term}</Content>
                  </DescriptionListTerm>
                  <DescriptionListDescription>
                    <Content>{result.definition}</Content>
                  </DescriptionListDescription>
                </DescriptionListGroup>
              ))}
            </DescriptionList>
          </SynPanel>
        </SynPageBody>
      )}
    </SynPage>
  )
}
