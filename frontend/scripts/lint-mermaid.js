#!/usr/bin/env node
/**
 * Validates every ```mermaid code block in Markdown files using
 * mermaid's built-in parse() with a happy-dom shim for Node.js.
 *
 * Usage:
 *   node scripts/lint-mermaid.js                 # lint all .md files
 *   node scripts/lint-mermaid.js docs/           # lint a directory
 *   node scripts/lint-mermaid.js a.md b.md       # lint specific files (lint-staged)
 *
 * Exit code: 0 if all pass, 1 if any fail.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

const { Window } = require('happy-dom')
const window = new Window({ url: 'https://localhost/' })

const defineGlobal = (name, value) => {
  Object.defineProperty(globalThis, name, {
    value,
    writable: true,
    configurable: true,
  })
}

defineGlobal('window', window)
defineGlobal('document', window.document)
defineGlobal('navigator', window.navigator)
defineGlobal('DOMParser', window.DOMParser)
defineGlobal('XMLSerializer', window.XMLSerializer)
defineGlobal('HTMLElement', window.HTMLElement)
defineGlobal('Element', window.Element)
defineGlobal('Node', window.Node)
defineGlobal('self', window)
if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0)
}

const mermaid = require('mermaid').default
mermaid.initialize({ startOnLoad: false, suppressErrors: true, securityLevel: 'loose' })

const MERMAID_BLOCK_RE = /```mermaid\s*\n([\s\S]*?)```/g

function extractBlocks(filePath) {
  const content = readFileSync(filePath, 'utf-8')
  const blocks = []
  let match
  const re = new RegExp(MERMAID_BLOCK_RE.source, MERMAID_BLOCK_RE.flags)
  while ((match = re.exec(content)) !== null) {
    const line = content.slice(0, match.index).split('\n').length
    blocks.push({ diagram: match[1].trim(), line, file: filePath })
  }
  return blocks
}

const EXCLUDED_DIRS = new Set(['node_modules', '.git'])

function findMarkdownFiles(dir) {
  return readdirSync(dir, { recursive: true })
    .filter((entry) => {
      if (!entry.endsWith('.md')) return false
      const parts = entry.split(/[\\/]/)
      return !parts.some((part) => EXCLUDED_DIRS.has(part))
    })
    .map((entry) => join(dir, entry))
    .sort()
}

function resolveFiles(args) {
  if (args.length === 0) {
    return findMarkdownFiles('.')
  }

  const files = []
  for (const arg of args) {
    try {
      const stat = statSync(arg)
      if (stat.isDirectory()) {
        files.push(...findMarkdownFiles(arg))
      } else if (arg.endsWith('.md')) {
        files.push(arg)
      }
    } catch {
      console.warn(`Warning: skipping ${arg} (not found)`)
    }
  }
  return files.sort()
}

async function main() {
  const args = process.argv.slice(2)
  const mdFiles = resolveFiles(args)

  const allBlocks = mdFiles.flatMap(extractBlocks)
  if (allBlocks.length === 0) {
    process.exit(0)
  }

  const fileCount = new Set(allBlocks.map((b) => b.file)).size
  console.log(`Validating ${allBlocks.length} mermaid diagrams across ${fileCount} files…\n`)

  let failures = 0

  for (const block of allBlocks) {
    try {
      await mermaid.parse(block.diagram)
      console.log(`  ✓  ${block.file}:${block.line}`)
    } catch (err) {
      failures++
      const msg = err?.message ?? String(err)
      const short = msg.split('\n').slice(0, 4).join('\n      ')
      console.log(`  ✗  ${block.file}:${block.line}`)
      console.log(`      ${short}`)
      console.log(`      ┄ preview: ${block.diagram.split('\n').slice(0, 2).join(' | ')}`)
      console.log()
    }
  }

  console.log(`\nResult: ${allBlocks.length - failures}/${allBlocks.length} passed, ${failures} failed.`)
  process.exit(failures > 0 ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(2)
})
