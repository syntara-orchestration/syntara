import { describe, expect, it } from 'vitest'

import { humanizeFormDefinitionIssueMessage, parseFormDefinitionErrorLocation } from './formDefinitionValidationMessage'

describe('parseFormDefinitionErrorLocation', () => {
  it('parses backend dotted field paths', () => {
    expect(parseFormDefinitionErrorLocation('parameters.form_definition.fields.0.value_name')).toEqual({
      fieldIndex: 0,
      propertyKey: 'value_name',
    })
  })

  it('parses option row paths', () => {
    expect(
      parseFormDefinitionErrorLocation('parameters.form_definition.fields.1.options.values.2.display_label')
    ).toEqual({
      fieldIndex: 1,
      optionIndex: 2,
      propertyKey: 'display_label',
    })
  })

  it('parses zod bracket field paths', () => {
    expect(parseFormDefinitionErrorLocation('fields[0].label')).toEqual({
      fieldIndex: 0,
      propertyKey: 'label',
    })
  })
})

describe('humanizeFormDefinitionIssueMessage', () => {
  it('includes field number for value name pattern errors', () => {
    expect(
      humanizeFormDefinitionIssueMessage(
        "String should match pattern '^[a-zA-Z_][a-zA-Z0-9_]*$'",
        'parameters.form_definition.fields.0.value_name'
      )
    ).toBe(
      'Field 1 — Value name must start with a letter or underscore, then use letters, numbers, or underscores only'
    )
  })

  it('includes field and option row for empty option labels', () => {
    expect(
      humanizeFormDefinitionIssueMessage(
        '"display_label" must not be empty',
        'parameters.form_definition.fields.0.options.values.1.display_label'
      )
    ).toBe('Field 1 — Option 2 — Option label is required')
  })

  it('includes field number for empty field labels', () => {
    expect(humanizeFormDefinitionIssueMessage('String must contain at least 1 character(s)', 'fields[2].label')).toBe(
      'Field 3 — Field label is required'
    )
  })

  it('omits field location for inline builder copy', () => {
    expect(
      humanizeFormDefinitionIssueMessage('String must contain at least 1 character(s)', 'fields[2].label', {
        includeFieldLocation: false,
      })
    ).toBe('Field label is required')
  })

  it('humanizes pydantic empty label messages with field context in banners', () => {
    expect(
      humanizeFormDefinitionIssueMessage(
        'String should have at least 1 character',
        'parameters.form_definition.fields.6.label'
      )
    ).toBe('Field 7 — Field label is required')
  })
})
