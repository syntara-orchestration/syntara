import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { collectMountedRouterRoutes } from './collect-routes'

const temporaryRoots: string[] = []
afterEach(() => {
  for (const root of temporaryRoots.splice(0)) rmSync(root, { recursive: true, force: true })
})

function collect(files: Record<string, string>) {
  const root = mkdtempSync(join(tmpdir(), 'route-graph-'))
  temporaryRoots.push(root)
  const sources = {
    'routes/__root.ts': `import { createRootRoute } from '@tanstack/react-router'
export const rootRoute = createRootRoute({})`,
    ...files,
  }
  for (const [file, source] of Object.entries(sources)) {
    const path = join(root, file)
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(path, source)
  }
  const treeSource = `import { rootRoute } from './routes/__root'
import { routes } from './routes/child'
export const buildTree = () => rootRoute.addChildren(routes)`
  return collectMountedRouterRoutes(join(root, 'routes'), treeSource)
}

function templates(result: ReturnType<typeof collect>) {
  return result.routes.map((route) => route.template).sort()
}

describe('mounted route graph', () => {
  it('resolves aliased imports, named and star re-exports, namespaces, and default exports', () => {
    const result = collect({
      'routes/parent.ts': `import { createRoute as route } from '@tanstack/react-router'
import { rootRoute as root } from './__root'
export const parent = route({ getParentRoute: () => root, path: '/settings' })`,
      'routes/barrel/named.ts': `export { parent as settings } from '../parent'`,
      'routes/barrel/index.ts': `export * from './named'`,
      'routes/category.ts': `import * as parents from './barrel'
export const category = createRoute({ getParentRoute: () => parents.settings, path: '/$category' })`,
      'routes/field.ts': `import { category as parent } from './category'
const field = createRoute({ getParentRoute() { return parent }, path: '/$field' })
export default field`,
      'routes/child.ts': `import { settings } from './barrel'
import { category } from './category'
import field from './field.js'
export const routes = [settings.addChildren([category.addChildren([field])])]`,
    })
    expect(templates(result)).toStrictEqual(['/settings', '/settings/$category', '/settings/$category/$field'])
    expect(result.routes.find((route) => route.template.endsWith('/$field'))?.parameters).toStrictEqual([
      'category',
      'field',
    ])
    expect(result.unmountedRouteFiles).toStrictEqual([])
  })

  it('resolves deep nesting across files without a depth limit', () => {
    const files: Record<string, string> = {}
    const depth = 30
    for (let i = 0; i < depth; i++) {
      const parentImport =
        i === 0 ? `import { rootRoute as parent } from './__root'` : `import { route as parent } from './level${i - 1}'`
      files[`routes/level${i}.ts`] = `${parentImport}
export const route = createRoute({ getParentRoute: () => parent, path: '/level${i}' })`
    }
    const imports = Array.from({ length: depth }, (_, i) => `import { route as r${i} } from './level${i}'`).join('\n')
    const nested = Array.from({ length: depth }, (_, i) => `r${i}`).reduceRight(
      (child, parent) => `${parent}.addChildren([${child}])`
    )
    files['routes/child.ts'] = `${imports}\nexport const routes = [${nested}]`
    const result = collect(files)
    expect(result.routes).toHaveLength(depth)
    expect(templates(result)).toContain(Array.from({ length: depth }, (_, i) => `/level${i}`).join(''))
    expect(result.unmountedRouteFiles).toStrictEqual([])
  })

  it('resolves a parent outside the routes folder without executing its module or CSS imports', () => {
    const result = collect({
      'layouts/settings.tsx': `import { rootRoute } from '../routes/__root'
import './page.css'
throw new Error('This module must not execute')
export const settings = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: () => <div /> })`,
      'routes/child.ts': `import { settings } from '../layouts/settings'
const category = createRoute({ getParentRoute: () => settings, path: '/$category' })
export const routes = [settings.addChildren([category])]`,
    })
    expect(templates(result)).toStrictEqual(['/settings', '/settings/$category'])
  })

  it('supports pathless layouts, typed root factories and index routes', () => {
    const result = collect({
      'routes/__root.ts': `import { createRootRouteWithContext as root } from '@tanstack/react-router'
export const rootRoute = root<{}>()({})`,
      'routes/child.ts': `import { rootRoute } from './__root'
const layout = createRoute({ getParentRoute: () => rootRoute, id: '_layout' })
const settings = createRoute({ getParentRoute: () => layout, path: 'settings' })
const index = createRoute({ getParentRoute: () => settings, path: '/' })
export const routes = [layout.addChildren([settings.addChildren([index])])]`,
    })
    expect(templates(result)).toStrictEqual(['/settings', '/settings/'])
  })

  it('does not mount unused declarations or unrelated re-exports', () => {
    const result = collect({
      'routes/parent.ts': `import { rootRoute } from './__root'
export const parent = createRoute({ getParentRoute: () => rootRoute, path: '/settings' })`,
      'routes/orphan.ts': `import { rootRoute } from './__root'
export const orphan = createRoute({ getParentRoute: () => rootRoute, path: '/orphan' })`,
      'routes/barrel.ts': `export * from './parent'
export * from './orphan'`,
      'routes/child.ts': `import { parent } from './barrel'
import { rootRoute } from './__root'
const unused = createRoute({ getParentRoute: () => rootRoute, path: '/unused' })
export const routes = [parent]`,
    })
    expect(templates(result)).toStrictEqual(['/settings'])
    expect(result.unmountedRouteFiles).toStrictEqual(['orphan.ts'])
  })

  it.each([
    ['missing parent', `getParentRoute: () => missing, path: '/child'`, /Could not resolve route reference/],
    ['missing callback', `path: '/child'`, /Missing getParentRoute/],
    ['dynamic parent', `getParentRoute: () => chooseParent(), path: '/child'`, /Unsupported route definition/],
    ['dynamic path', `getParentRoute: () => rootRoute, path: makePath()`, /Expected a literal route path/],
  ])('fails explicitly for %s instead of emitting a guessed URL', (_name, options, message) => {
    expect(() =>
      collect({
        'routes/child.ts': `import { rootRoute } from './__root'
export const routes = [createRoute({ ${options} })]`,
      })
    ).toThrow(message)
  })

  it('does not treat an unresolved import named rootRoute as the root', () => {
    expect(() =>
      collect({
        'routes/child.ts': `import { missing as rootRoute } from './missing-module'
export const routes = [createRoute({ getParentRoute: () => rootRoute, path: '/child' })]`,
      })
    ).toThrow(/Could not resolve route reference/)
  })

  it('rejects parent cycles across module boundaries', () => {
    expect(() =>
      collect({
        'routes/parent.ts': `import { child } from './child'
export const parent = createRoute({ getParentRoute: () => child, path: '/parent' })`,
        'routes/child.ts': `import { parent } from './parent'
export const child = createRoute({ getParentRoute: () => parent, path: '/child' })
export const routes = [child]`,
      })
    ).toThrow(/Cyclic route parent reference/)
  })

  it('rejects cyclic route arrays', () => {
    expect(() => collect({ 'routes/child.ts': `export const routes = [...routes]` })).toThrow(
      /Cyclic route collection reference/
    )
  })
})
