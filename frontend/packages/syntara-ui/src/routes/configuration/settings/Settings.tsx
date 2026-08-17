import { ActionGroup, Alert, Button, Stack, StackItem, Tab } from '@patternfly/react-core'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsSettingsCategory, breadcrumbsSettingsPage } from '../../../app/breadcrumbBuilders'
import { settingsClient } from '../../../client'
import { EmptyStateAccessDenied } from '../../../components/EmptyStateAccessDenied'
import { NxPage, NxPageBody } from '../../../components/layout/NxPage'
import { NxPageHeader } from '../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../components/layout/NxPanel'
import { NxPageTitle } from '../../../components/NxPageTitle'
import { useQueryState } from '../../../components/states/useQueryState'
import { NxUrlTabs } from '../../../components/tabs/NxUrlTabs'
import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import {
  FILE_STORAGE_UNAVAILABLE_MESSAGE,
  FILE_STORAGE_UNCONFIGURED_MESSAGE,
  useFileStorageStatus,
} from '../../../hooks/useFileStorageStatus'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { useAlerts } from '../../../providers/alerts'
import { getErrorCode, isForbiddenError } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'

import { SettingsCategoryTab } from './SettingsCategoryTab'
import { useAllSettings } from './useAllSettings'
import { useSettingsPermissions } from './useSettingsPermissions'

const basePath = AppRoute.SystemAdministration.Settings

function buildBulkUpdates(
  edits: Map<string, unknown>,
  allSettings: { key: string; version: number }[]
): Array<{ key: string; value: unknown; expected_version: number }> {
  return Array.from(edits.entries()).reduce<Array<{ key: string; value: unknown; expected_version: number }>>(
    (acc, [key, value]) => {
      const setting = allSettings.find((s) => s.key === key)
      if (setting) acc.push({ key, value, expected_version: setting.version })
      return acc
    },
    []
  )
}

function FileStorageAlert() {
  const { isConfigured, status } = useFileStorageStatus()
  if (isConfigured) return null
  const message = status === 'unconfigured' ? FILE_STORAGE_UNCONFIGURED_MESSAGE : FILE_STORAGE_UNAVAILABLE_MESSAGE
  return <Alert variant="warning" isInline title={message} />
}

export default function Settings() {
  const settingsDocLink = useDocLink('settings')
  const [edits, setEdits] = useState<Map<string, unknown>>(new Map())
  const [validationErrors, setValidationErrors] = useState<Set<string>>(new Set())
  const { showError } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const { canRead, canWrite } = useSettingsPermissions()

  const categoriesQuery = settingsClient.useQuery('get', '/settings/categories', { enabled: canRead })
  const {
    settings: allSettings,
    isLoading: settingsLoading,
    error: settingsError,
    refetch: refetchSettings,
  } = useAllSettings({ enabled: canRead })

  const { mutate: bulkUpdate, isPending: isSaving } = settingsClient.useMutation('patch', '/settings')

  const isForbidden = isForbiddenError(categoriesQuery.error) || isForbiddenError(settingsError)

  const categoriesState = useQueryState(categoriesQuery, {
    title: 'Error loading setting categories',
    onRetry: () => detachPromise(categoriesQuery.refetch()),
  })
  const settingsState = useQueryState(
    { error: settingsError, isPending: settingsLoading, refetch: refetchSettings },
    {
      title: 'Error loading settings',
      onRetry: () => detachPromise(refetchSettings()),
    }
  )

  const categories = useMemo(() => categoriesQuery.data?.resources ?? [], [categoriesQuery.data])
  const validTabs = useMemo(() => categories.map((c) => c.slug), [categories])
  const defaultCategory = categories[0]?.slug ?? ''
  const [activeSlug] = useUrlTab(basePath, defaultCategory)
  const location = useRouterState({ select: (s) => s.location.pathname })
  const navigate = useNavigate()

  // UrlTabs only redirects when the URL contains an *invalid* tab slug.
  // When there is *no* slug at all, useUrlTab silently falls back to defaultTab
  // without updating the URL — so we redirect here to keep the URL bookmarkable.
  useEffect(() => {
    if (defaultCategory && location.startsWith(basePath) && !location.startsWith(`${basePath}/`)) {
      detachPromise(navigate({ to: `${basePath}/${defaultCategory}`, replace: true }))
    }
  }, [defaultCategory, location, navigate])

  const activeIndex = useMemo(() => {
    const idx = categories.findIndex((c) => c.slug === activeSlug)
    return Math.max(idx, 0)
  }, [activeSlug, categories])

  const settingsBreadcrumbs = useMemo(() => {
    const category = categories[activeIndex]
    if (category && activeIndex > 0) {
      return breadcrumbsSettingsCategory(category.name)
    }
    return breadcrumbsSettingsPage()
  }, [categories, activeIndex])

  const settingsByCategory = useMemo(() => {
    const grouped = new Map<string, (typeof allSettings)[number][]>()
    for (const setting of allSettings) {
      const cat = setting.category
      if (!grouped.has(cat)) grouped.set(cat, [])
      grouped.get(cat)!.push(setting)
    }
    return grouped
  }, [allSettings])

  const handleChange = useCallback((key: string, value: unknown) => {
    setEdits((prev) => {
      const next = new Map(prev)
      next.set(key, value)
      return next
    })
  }, [])

  const handleValidationChange = useCallback((key: string, hasError: boolean) => {
    setValidationErrors((prev) => {
      const next = new Set(prev)
      if (hasError) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const handleResetField = useCallback(
    (key: string) => {
      const setting = allSettings.find((s) => s.key === key)
      if (!setting) return
      setEdits((prev) => {
        const next = new Map(prev)
        next.set(key, setting.default_value)
        return next
      })
    },
    [allSettings]
  )

  const handleSave = useCallback(() => {
    bulkUpdate(
      { body: { updates: buildBulkUpdates(edits, allSettings) } },
      {
        onSuccess: () => {
          setEdits(new Map())
          detachPromise(refetchSettings())
        },
        onError: (err) => {
          if (getErrorCode(err) === 'SETTING_VERSION_CONFLICT') {
            showError({
              title: 'Version conflict',
              description: 'Settings were modified by another user. The page has been refreshed.',
            })
            detachPromise(refetchSettings())
            setEdits(new Map())
          } else {
            handleMutationError({ title: 'Save failed' })(err)
          }
        },
      }
    )
  }, [edits, allSettings, bulkUpdate, showError, handleMutationError, refetchSettings])

  const hasChanges = edits.size > 0
  const hasValidationErrors = validationErrors.size > 0

  useDirtyFormGuard({
    isDirty: hasChanges,
    onDiscard: () => setEdits(new Map()),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved setting changes. Your changes will be lost if you leave.',
  })

  if (!canRead || isForbidden) {
    return (
      <NxPage>
        <NxPageTitle segments={['Settings']} />
        <NxPageHeader title="Settings" docLink={settingsDocLink} breadcrumbs={breadcrumbsSettingsPage()} />
        <StackItem isFilled>
          <NxPanel isFullHeight>
            <EmptyStateAccessDenied description="You don't have permission to view settings. Contact your administrator to request the auditor or admin role." />
          </NxPanel>
        </StackItem>
      </NxPage>
    )
  }

  const errorOrLoadingState = categoriesState ?? settingsState
  if (errorOrLoadingState) {
    return (
      <NxPage>
        <NxPageTitle segments={['Settings']} />
        <NxPageHeader title="Settings" docLink={settingsDocLink} breadcrumbs={breadcrumbsSettingsPage()} />
        <NxPageBody>
          <NxPanel isFullHeight>{errorOrLoadingState}</NxPanel>
        </NxPageBody>
      </NxPage>
    )
  }

  return (
    <NxPage>
      <NxPageTitle segments={['Settings']} />
      <NxPageHeader title="Settings" docLink={settingsDocLink} breadcrumbs={settingsBreadcrumbs} />
      <NxPageBody>
        <FileStorageAlert />
        <NxPanel
          isFullHeight
          panelMainBodyProps={{ style: { flex: 1, minHeight: 0 } }}
          footer={
            canWrite ? (
              <ActionGroup>
                <Button
                  variant="primary"
                  onClick={handleSave}
                  isDisabled={!hasChanges || isSaving || hasValidationErrors}
                  isLoading={isSaving}
                >
                  Save changes
                </Button>
              </ActionGroup>
            ) : undefined
          }
        >
          <Stack hasGutter style={{ flex: 1, minHeight: 0, height: '100%' }}>
            <StackItem>
              <NxUrlTabs
                basePath={basePath}
                defaultTab={defaultCategory}
                validTabs={validTabs}
                aria-label="Settings categories"
              >
                {categories.map((cat) => (
                  <Tab key={cat.slug} eventKey={cat.slug} title={cat.name} />
                ))}
              </NxUrlTabs>
            </StackItem>
            <NxPageBody style={{ overflow: 'auto', padding: 'var(--pf-t--global--spacer--md)' }}>
              {categories[activeIndex] && (
                <SettingsCategoryTab
                  settings={settingsByCategory.get(categories[activeIndex].slug) ?? []}
                  edits={edits}
                  onChange={handleChange}
                  onResetField={handleResetField}
                  onValidationChange={handleValidationChange}
                  readOnly={!canWrite}
                />
              )}
            </NxPageBody>
          </Stack>
        </NxPanel>
      </NxPageBody>
    </NxPage>
  )
}
