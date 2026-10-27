import { IntegrationTypeEnum, type IntegrationsAPI } from '@syntara/contracts'

/** The UI supports both independent v1 resources; neither API widens the other. */
export type IntegrationRead =
  | IntegrationsAPI.components['schemas']['IntegrationRead']
  | IntegrationsAPI.components['schemas']['KafkaIntegrationRead']

export type IntegrationConfiguration =
  | IntegrationsAPI.components['schemas']['IntegrationCreate']['configuration']
  | (IntegrationsAPI.components['schemas']['KafkaConfiguration'] & {
      integration_type: typeof IntegrationTypeEnum.KAFKA
    })
