import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import syntaraPlugin from '../index.js'
import rule from '../rules/no-route-navigation-callbacks.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  plugins: { syntara: syntaraPlugin },
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

ruleTester.run('syntara/no-route-navigation-callbacks', rule, {
  valid: [
    { code: '<Button onClick={() => setDialogOpen(true)}>Create</Button>' },
    { code: "<Button onClick={() => { save(); navigate({ to: '/users' }) }}>Save</Button>" },
    { code: "<SynLink to='/users/new'>Create</SynLink>" },
    { code: '<DropdownItem onClick={() => setDialogOpen(true)}>Open</DropdownItem>' },
    { code: '<Toolbar onEdit={() => openEditDialog()}/>' },
    { code: "<Toolbar onNavigate={() => navigate({ to: '/users' })}/>" },
    { code: "<Wizard onCancel={() => navigate({ to: '/users' })}/>" },
  ],
  invalid: [
    {
      code: "<Button onClick={() => navigate({ to: '/users/new' })}>Create</Button>",
      errors: [{ messageId: 'useLink' }],
    },
    {
      code: "const goToEdit = () => detachPromise(navigate({ to: '/users/1/edit' })); <Toolbar onEdit={goToEdit}/>",
      errors: [{ messageId: 'useLink' }],
    },
    {
      code: "const goToCreate = () => navigate({ to: '/users/new' }); <SynEmptyStateNoData addData={goToCreate}/>",
      errors: [{ messageId: 'useLink' }],
    },
    {
      code: "<Toolbar onBack={() => navigate({ to: '/users' })}/>",
      errors: [{ messageId: 'useLink' }],
    },
    {
      code: "<DropdownItem onClick={() => navigate({ to: '/users' })}>Open</DropdownItem>",
      errors: [{ messageId: 'useLink' }],
    },
    {
      code: "<MenuItem onClick={() => navigate({ to: '/users' })}>Open</MenuItem>",
      errors: [{ messageId: 'useLink' }],
    },
  ],
})
