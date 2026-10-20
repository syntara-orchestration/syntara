import { z } from 'zod'

const optionalUrl = z.string().url('Must be a valid URL').or(z.literal(''))

const claimMappingSchema = z.object({
  subject: z.string().min(1, 'Subject claim is required'),
  email: z.string().min(1, 'Email claim is required'),
  username: z.string().min(1, 'Username claim is required'),
  firstName: z.string().min(1, 'First name claim is required'),
  lastName: z.string().min(1, 'Last name claim is required'),
})

const groupMappingEntrySchema = z.object({
  idpGroupValue: z.string().min(1, 'IdP group value is required'),
  mappedGroupId: z.string().uuid('Must be a valid group ID'),
})

const groupMappingSchema = z
  .object({
    jmespathExpression: z.string().min(1, 'Group extraction expression is required'),
    entries: z.array(groupMappingEntrySchema),
  })
  .nullable()

const baseFields = {
  idpType: z.string().min(1, 'Provider type is required'),
  name: z.string().min(1, 'Provider name is required'),
  enabled: z.boolean(),
  autoDiscovery: z.boolean(),
  issuerUrl: z.string().min(1, 'Issuer URL is required').url('Issuer URL must be a valid URL'),
  clientId: z.string().min(1, 'Client ID is required'),
  scopes: z.string().min(1, 'Scopes are required'),
  // Manual endpoint fields (required when autoDiscovery is off)
  authorizationEndpoint: optionalUrl,
  tokenEndpoint: optionalUrl,
  jwksUri: optionalUrl,
  userinfoEndpoint: optionalUrl,
  endSessionEndpoint: optionalUrl,
  // Single logout
  enableRpInitiatedLogout: z.boolean(),
  claimMapping: claimMappingSchema,
  groupMapping: groupMappingSchema,
  allowAllAuthenticated: z.boolean(),
  aapRoleMappingEnabled: z.boolean(),
  disableTlsVerify: z.boolean(),
}

const manualEndpointRefinement = (
  data: {
    autoDiscovery: boolean
    authorizationEndpoint: string
    tokenEndpoint: string
    jwksUri: string
    endSessionEndpoint: string
    enableRpInitiatedLogout: boolean
  },
  ctx: z.RefinementCtx
) => {
  if (!data.autoDiscovery) {
    if (!data.authorizationEndpoint) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Required when auto-discovery is disabled',
        path: ['authorizationEndpoint'],
      })
    }
    if (!data.tokenEndpoint) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Required when auto-discovery is disabled',
        path: ['tokenEndpoint'],
      })
    }
    if (!data.jwksUri) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Required when auto-discovery is disabled',
        path: ['jwksUri'],
      })
    }
    if (data.enableRpInitiatedLogout && !data.endSessionEndpoint) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Required when single logout is enabled and auto-discovery is disabled',
        path: ['endSessionEndpoint'],
      })
    }
  }
}

export const identityProviderAddSchema = z
  .object({
    ...baseFields,
    clientSecret: z.string().min(1, 'Client Secret is required'),
  })
  .superRefine(manualEndpointRefinement)

export const identityProviderEditSchema = z
  .object({
    ...baseFields,
    clientSecret: z.string(),
  })
  .superRefine(manualEndpointRefinement)

export type IdentityProviderFormData = z.infer<typeof identityProviderAddSchema>

export const identityProviderDefaults: IdentityProviderFormData = {
  idpType: '',
  name: '',
  enabled: false,
  autoDiscovery: true,
  issuerUrl: '',
  clientId: '',
  clientSecret: '',
  scopes: 'openid profile email',
  authorizationEndpoint: '',
  tokenEndpoint: '',
  jwksUri: '',
  userinfoEndpoint: '',
  endSessionEndpoint: '',
  enableRpInitiatedLogout: false,
  claimMapping: {
    subject: 'sub',
    email: 'email',
    username: 'preferred_username',
    firstName: 'given_name',
    lastName: 'family_name',
  },
  groupMapping: null,
  allowAllAuthenticated: false,
  aapRoleMappingEnabled: false,
  disableTlsVerify: false,
}
