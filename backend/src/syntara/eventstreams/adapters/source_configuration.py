"""Select supported source configuration variants without importing broker clients."""

from typing import Annotated

from pydantic import Field

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration

# This feature has one variant; later transports extend this tagged contract and
# add their own addressing fields rather than inheriting Kafka's topic/group.
# The bare alias is the model column annotation; the annotated form (with the
# discriminator) is only handed to DiscriminatedJSONB — mirroring the Integration
# configuration pattern so SQLModel preserves the sa_type override.
SourceConfigurationTypes = KafkaSourceConfiguration
SourceConfiguration = Annotated[SourceConfigurationTypes, Field(discriminator="transport")]
