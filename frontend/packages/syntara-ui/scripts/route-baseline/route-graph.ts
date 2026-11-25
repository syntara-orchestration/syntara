import { readdirSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import ts from 'typescript'

import type { ParsedCreateRoute } from './route-manifest-schema'

type ReadRedirect = (source: string) => string | undefined

/** Parse route declarations without executing page components, CSS, or callbacks. */
class RouteGraph {
  private readonly program: ts.Program
  private readonly checker: ts.TypeChecker
  private readonly entryFile: string
  private readonly readRedirect: ReadRedirect
  private readonly paths = new Map<ts.CallExpression, string>()
  readonly visitedFiles = new Set<string>()

  constructor(entryFile: string, source: string, files: string[], readRedirect: ReadRedirect) {
    this.entryFile = entryFile
    this.readRedirect = readRedirect
    const options: ts.CompilerOptions = {
      noLib: true,
      noEmit: true,
      jsx: ts.JsxEmit.Preserve,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      target: ts.ScriptTarget.Latest,
    }
    const host = ts.createCompilerHost(options)
    const readFile = host.readFile
    host.readFile = (file) => (resolve(file) === entryFile ? source : readFile(file))
    // External packages provide factories/components, not local route declarations.
    // Their implementations and type libraries are unnecessary for symbol resolution.
    host.resolveModuleNames = (names, containingFile) =>
      names.map((name) =>
        name.startsWith('.') ? ts.resolveModuleName(name, containingFile, options, host).resolvedModule : undefined
      )
    this.program = ts.createProgram([entryFile, ...files], options, host)
    this.checker = this.program.getTypeChecker()
  }

  private source(file: string): ts.SourceFile {
    const source = this.program.getSourceFile(file)
    if (!source) throw new Error(`Could not read route module ${file}`)
    return source
  }

  private fail(node: ts.Node, message: string): never {
    const file = node.getSourceFile()
    const { line } = file.getLineAndCharacterOfPosition(node.getStart())
    throw new Error(`${message} in ${file.fileName}:${line + 1}: ${node.getText(file)}`)
  }

  private factory(node: ts.Expression): string | undefined {
    if (ts.isCallExpression(node)) return this.factory(node.expression)
    const name = ts.isPropertyAccessExpression(node) ? node.name : node
    if (!ts.isIdentifier(name)) return undefined
    const symbol = this.checker.getSymbolAtLocation(name)
    const imported = symbol?.declarations?.find(ts.isImportSpecifier)
    return imported ? (imported.propertyName ?? imported.name).text : name.text
  }

  private dereference(input: ts.Expression, seen = new Set<ts.Node>()): ts.Expression {
    const node = unwrap(input)
    if (!ts.isIdentifier(node) && !ts.isPropertyAccessExpression(node)) return node
    if (seen.has(node)) return this.fail(node, 'Cyclic route reference')
    seen.add(node)
    let symbol = this.checker.getSymbolAtLocation(ts.isPropertyAccessExpression(node) ? node.name : node)
    if (symbol && symbol.flags & ts.SymbolFlags.Alias) symbol = this.checker.getAliasedSymbol(symbol)
    const declaration = symbol?.valueDeclaration ?? symbol?.declarations?.[0]
    if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer) {
      return this.dereference(declaration.initializer, seen)
    }
    if (declaration && ts.isExportAssignment(declaration)) return this.dereference(declaration.expression, seen)
    return this.fail(node, 'Could not resolve route reference')
  }

  private route(input: ts.Expression): ts.CallExpression {
    const node = this.dereference(input)
    if (ts.isCallExpression(node)) {
      if (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 'addChildren') {
        return this.route(node.expression.expression)
      }
      if (
        ['createRoute', 'createRootRoute', 'createRootRouteWithContext'].includes(this.factory(node.expression) ?? '')
      ) {
        return node
      }
    }
    return this.fail(node, 'Unsupported route definition')
  }

  private path(call: ts.CallExpression, ancestors = new Set<ts.Node>()): string {
    const cached = this.paths.get(call)
    if (cached !== undefined) return cached
    if (ancestors.has(call)) return this.fail(call, 'Cyclic route parent reference')
    const next = new Set(ancestors).add(call)
    this.visitedFiles.add(call.getSourceFile().fileName)
    const factory = this.factory(call.expression)
    if (factory === 'createRootRoute' || factory === 'createRootRouteWithContext') {
      this.paths.set(call, '')
      return ''
    }
    const options = call.arguments[0]
    if (!options || !ts.isObjectLiteralExpression(options)) return this.fail(call, 'Expected literal route options')
    const parent = property(options, 'getParentRoute')
    let prefix = ''
    if (parent) {
      const callback = ts.isPropertyAssignment(parent) ? unwrap(parent.initializer) : parent
      if (!ts.isArrowFunction(callback) && !ts.isFunctionExpression(callback) && !ts.isMethodDeclaration(callback)) {
        return this.fail(parent, 'Unsupported getParentRoute callback')
      }
      const body = callback.body
      const expression =
        body && ts.isBlock(body)
          ? body.statements.length === 1 && ts.isReturnStatement(body.statements[0])
            ? body.statements[0].expression
            : undefined
          : body
      if (!expression) return this.fail(parent, 'Expected getParentRoute to return a route reference')
      const parentRoute = this.route(expression)
      prefix = this.path(parentRoute, next)
    } else {
      return this.fail(call, 'Missing getParentRoute')
    }
    const pathProperty = property(options, 'path')
    let segment = ''
    if (pathProperty) {
      if (!ts.isPropertyAssignment(pathProperty) || !ts.isStringLiteralLike(unwrap(pathProperty.initializer))) {
        return this.fail(pathProperty, 'Expected a literal route path')
      }
      const value = unwrap(pathProperty.initializer)
      if (ts.isStringLiteralLike(value)) segment = value.text
    } else if (!property(options, 'id')) {
      return this.fail(call, 'Expected route path or pathless layout id')
    }
    const fullPath = segment ? `${prefix.replace(/\/$/, '')}/${segment.replace(/^\//, '')}` : prefix
    this.paths.set(call, fullPath)
    return fullPath
  }

  private parsed(call: ts.CallExpression): ParsedCreateRoute | undefined {
    const path = this.path(call)
    if (!path) return undefined // The root is not a bookmarkable page.
    const options = call.arguments[0]
    const beforeLoad = options && ts.isObjectLiteralExpression(options) ? property(options, 'beforeLoad') : undefined
    const redirectTo = beforeLoad ? this.readRedirect(beforeLoad.getText()) : undefined
    return redirectTo ? { path, kind: 'redirect', redirectTo } : { path, kind: 'page' }
  }

  /** Resolve route arrays, spreads, and addChildren calls actually mounted in the tree. */
  private mounted(input: ts.Expression, seen = new Set<ts.Node>()): ParsedCreateRoute[] {
    const node = this.dereference(input)
    if (seen.has(node)) return this.fail(node, 'Cyclic route collection reference')
    const next = new Set(seen).add(node)
    this.visitedFiles.add(node.getSourceFile().fileName)
    if (ts.isArrayLiteralExpression(node)) {
      return node.elements.flatMap((item) => this.mounted(ts.isSpreadElement(item) ? item.expression : item, next))
    }
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      node.expression.name.text === 'addChildren'
    ) {
      const children = node.arguments[0]
      if (!children) return this.fail(node, 'Missing addChildren routes')
      return [...this.mounted(node.expression.expression, next), ...this.mounted(children, next)]
    }
    const call = this.route(node)
    const parsed = this.parsed(call)
    return parsed ? [parsed] : []
  }

  declarations(file: string): ts.CallExpression[] {
    const calls: ts.CallExpression[] = []
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && this.factory(node.expression) === 'createRoute') calls.push(node)
      ts.forEachChild(node, visit)
    }
    visit(this.source(file))
    return calls
  }

  parseSource(): ParsedCreateRoute[] {
    return this.declarations(this.entryFile).flatMap((call) => this.parsed(call) ?? [])
  }

  tree(): ParsedCreateRoute[] {
    const mounts: ts.CallExpression[] = []
    const visit = (node: ts.Node) => {
      if (
        ts.isCallExpression(node) &&
        ts.isPropertyAccessExpression(node.expression) &&
        node.expression.name.text === 'addChildren'
      ) {
        mounts.push(node)
        return
      }
      ts.forEachChild(node, visit)
    }
    visit(this.source(this.entryFile))
    if (mounts.length !== 1) throw new Error('Expected one mounted root addChildren call in the route tree')
    return this.mounted(mounts[0])
  }
}

function unwrap(node: ts.Expression): ts.Expression {
  if (
    ts.isParenthesizedExpression(node) ||
    ts.isAsExpression(node) ||
    ts.isSatisfiesExpression(node) ||
    ts.isNonNullExpression(node)
  ) {
    return unwrap(node.expression)
  }
  return node
}

function property(options: ts.ObjectLiteralExpression, name: string): ts.ObjectLiteralElementLike | undefined {
  return options.properties.find(
    (entry) =>
      entry.name && (ts.isIdentifier(entry.name) || ts.isStringLiteralLike(entry.name)) && entry.name.text === name
  )
}

function routeFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return routeFiles(path)
    return /\.tsx?$/.test(entry.name) && !entry.name.includes('.test.') ? [path] : []
  })
}

export function parseRouteSource(source: string, readRedirect: ReadRedirect): ParsedCreateRoute[] {
  const file = resolve('__route_source__.tsx')
  return new RouteGraph(file, source, [], readRedirect).parseSource()
}

export function collectRouteGraph(routesDir: string, treeSource: string, readRedirect: ReadRedirect) {
  const files = routeFiles(resolve(routesDir))
  const graph = new RouteGraph(resolve(routesDir, '../tanstackRouteTree.tsx'), treeSource, files, readRedirect)
  const routes = graph.tree()
  const unmountedRouteFiles = files
    .filter((file) => !graph.visitedFiles.has(file) && graph.declarations(file).length > 0)
    .map((file) => relative(routesDir, file))
    .sort()
  return { routes, unmountedRouteFiles }
}
