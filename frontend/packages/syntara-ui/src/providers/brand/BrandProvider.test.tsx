import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import type { BrandConfig } from './brandConfig'
import { BrandProvider } from './BrandProvider'
import { useBrand } from './useBrand'

function BrandConsumer() {
  const brand = useBrand()
  return <span data-testid="app-title">{brand.appTitle}</span>
}

function FullBrandConsumer() {
  const brand = useBrand()
  return (
    <>
      <span data-testid="app-title">{brand.appTitle}</span>
      <span data-testid="shell-theme">{brand.shellTheme}</span>
      <span data-testid="favicon">{brand.faviconPath}</span>
      <span data-testid="logo-light">{brand.logoExpandedLight}</span>
      <span data-testid="logo-dark">{brand.logoExpandedDark}</span>
      <span data-testid="logo-collapsed">{brand.logoCollapsed}</span>
      <span data-testid="login-light">{brand.logoLoginLight}</span>
      <span data-testid="login-dark">{brand.logoLoginDark}</span>
    </>
  )
}

function LoginBrandConsumer() {
  const brand = useBrand()
  return (
    <>
      <span data-testid="login-light">{brand.logoLoginLight}</span>
      <span data-testid="login-dark">{brand.logoLoginDark}</span>
    </>
  )
}

describe('BrandProvider', () => {
  it('provides the default brand config', () => {
    render(
      <BrandProvider>
        <BrandConsumer />
      </BrandProvider>
    )
    expect(screen.getByTestId('app-title')).toHaveTextContent('Syntara')
  })

  it('uses the same community login asset for light and dark', () => {
    render(
      <BrandProvider>
        <LoginBrandConsumer />
      </BrandProvider>
    )
    const light = screen.getByTestId('login-light').textContent
    const dark = screen.getByTestId('login-dark').textContent
    expect(light).toBeTruthy()
    expect(light).toBe(dark)
    expect(light).toMatch(/login/)
  })

  it('accepts a custom config override', () => {
    const customConfig: BrandConfig = {
      appTitle: 'Custom Product',
      faviconPath: '/custom-favicon.svg',
      logoExpandedLight: '/custom-logo-light.svg',
      logoExpandedDark: '/custom-logo-dark.svg',
      logoCollapsed: '/custom-icon.svg',
      logoLoginLight: '/custom-login-light.svg',
      logoLoginDark: '/custom-login-dark.svg',
      shellTheme: 'default',
    }
    render(
      <BrandProvider config={customConfig}>
        <BrandConsumer />
      </BrandProvider>
    )
    expect(screen.getByTestId('app-title')).toHaveTextContent('Custom Product')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <BrandProvider>
        <BrandConsumer />
      </BrandProvider>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('favicon sync', () => {
    let faviconLink: HTMLLinkElement

    beforeEach(() => {
      faviconLink = document.createElement('link')
      faviconLink.rel = 'icon'
      faviconLink.href = '/old-favicon.svg'
      document.head.appendChild(faviconLink)
    })

    afterEach(() => {
      faviconLink.remove()
    })

    it('updates the favicon link href from default config', () => {
      render(
        <BrandProvider>
          <BrandConsumer />
        </BrandProvider>
      )
      expect(faviconLink.href).toContain('icon')
    })

    it('updates the favicon link href from custom config', () => {
      const customConfig: BrandConfig = {
        appTitle: 'Custom',
        faviconPath: '/custom-favicon.svg',
        logoExpandedLight: '/logo-light.svg',
        logoExpandedDark: '/logo-dark.svg',
        logoCollapsed: '/icon.svg',
        logoLoginLight: '/login-light.svg',
        logoLoginDark: '/login-dark.svg',
        shellTheme: 'default',
      }
      render(
        <BrandProvider config={customConfig}>
          <BrandConsumer />
        </BrandProvider>
      )
      expect(faviconLink.href).toContain('/custom-favicon.svg')
    })
  })

  describe('shell theme', () => {
    const feltShellConfig: BrandConfig = {
      appTitle: 'Custom Product',
      faviconPath: '/custom-favicon.svg',
      logoExpandedLight: '/custom-logo-light.svg',
      logoExpandedDark: '/custom-logo-dark.svg',
      logoCollapsed: '/custom-icon.svg',
      logoLoginLight: '/custom-login-light.svg',
      logoLoginDark: '/custom-login-dark.svg',
      shellTheme: 'felt',
    }

    afterEach(() => {
      document.documentElement.classList.remove('pf-v6-theme-felt')
    })

    it('does not add pf-v6-theme-felt by default (community/upstream)', () => {
      render(
        <BrandProvider>
          <BrandConsumer />
        </BrandProvider>
      )
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(false)
    })

    it('adds pf-v6-theme-felt for product config', () => {
      render(
        <BrandProvider config={feltShellConfig}>
          <BrandConsumer />
        </BrandProvider>
      )
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(true)
    })

    it('removes pf-v6-theme-felt on unmount', () => {
      const { unmount } = render(
        <BrandProvider config={feltShellConfig}>
          <BrandConsumer />
        </BrandProvider>
      )
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(true)
      unmount()
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(false)
    })
  })

  describe('upstream defaults (no brand config)', () => {
    it('shows community app title', () => {
      render(
        <BrandProvider>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('app-title')).toHaveTextContent('Syntara')
    })

    it('uses default shell theme (no Felt)', () => {
      render(
        <BrandProvider>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('shell-theme')).toHaveTextContent('default')
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(false)
    })

    it('points favicon at community icon', () => {
      render(
        <BrandProvider>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('favicon').textContent).toMatch(/icon/)
    })

    it('uses identical login assets for light and dark', () => {
      render(
        <BrandProvider>
          <FullBrandConsumer />
        </BrandProvider>
      )
      const light = screen.getByTestId('login-light').textContent
      const dark = screen.getByTestId('login-dark').textContent
      expect(light).toBe(dark)
    })
  })

  describe('product config (brand config with product values)', () => {
    const productConfig: BrandConfig = {
      appTitle: 'Custom Product',
      faviconPath: '/custom-favicon.svg',
      logoExpandedLight: '/custom-logo-light.svg',
      logoExpandedDark: '/custom-logo-dark.svg',
      logoCollapsed: '/custom-icon.svg',
      logoLoginLight: '/custom-login-light.svg',
      logoLoginDark: '/custom-login-dark.svg',
      shellTheme: 'felt',
    }

    afterEach(() => {
      document.documentElement.classList.remove('pf-v6-theme-felt')
    })

    it('shows product app title', () => {
      render(
        <BrandProvider config={productConfig}>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('app-title')).toHaveTextContent('Custom Product')
    })

    it('applies Felt theme', () => {
      render(
        <BrandProvider config={productConfig}>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('shell-theme')).toHaveTextContent('felt')
      expect(document.documentElement.classList.contains('pf-v6-theme-felt')).toBe(true)
    })

    it('uses product favicon', () => {
      render(
        <BrandProvider config={productConfig}>
          <FullBrandConsumer />
        </BrandProvider>
      )
      expect(screen.getByTestId('favicon')).toHaveTextContent('/custom-favicon.svg')
    })

    it('uses distinct login assets for light and dark', () => {
      render(
        <BrandProvider config={productConfig}>
          <FullBrandConsumer />
        </BrandProvider>
      )
      const light = screen.getByTestId('login-light').textContent
      const dark = screen.getByTestId('login-dark').textContent
      expect(light).toBe('/custom-login-light.svg')
      expect(dark).toBe('/custom-login-dark.svg')
      expect(light).not.toBe(dark)
    })

    it('has no accessibility violations', async () => {
      const { container } = render(
        <BrandProvider config={productConfig}>
          <FullBrandConsumer />
        </BrandProvider>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
