from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.oidc_test_result_claim_aliases_type_0 import OIDCTestResultClaimAliasesType0
    from ..models.oidc_test_result_metadata_type_0 import OIDCTestResultMetadataType0


T = TypeVar("T", bound="OIDCTestResult")


@_attrs_define
class OIDCTestResult:
    """Result of an OIDC connection test.

    Attributes:
        success (bool):
        message (str):
        metadata (None | OIDCTestResultMetadataType0 | Unset):
        claims_supported (list[str] | None | Unset):
        claim_aliases (None | OIDCTestResultClaimAliasesType0 | Unset):
        end_session_endpoint_supported (bool | Unset):  Default: False.
    """

    success: bool
    message: str
    metadata: None | OIDCTestResultMetadataType0 | Unset = UNSET
    claims_supported: list[str] | None | Unset = UNSET
    claim_aliases: None | OIDCTestResultClaimAliasesType0 | Unset = UNSET
    end_session_endpoint_supported: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.oidc_test_result_claim_aliases_type_0 import OIDCTestResultClaimAliasesType0
        from ..models.oidc_test_result_metadata_type_0 import OIDCTestResultMetadataType0

        success = self.success

        message = self.message

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, OIDCTestResultMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        claims_supported: list[str] | None | Unset
        if isinstance(self.claims_supported, Unset):
            claims_supported = UNSET
        elif isinstance(self.claims_supported, list):
            claims_supported = self.claims_supported

        else:
            claims_supported = self.claims_supported

        claim_aliases: dict[str, Any] | None | Unset
        if isinstance(self.claim_aliases, Unset):
            claim_aliases = UNSET
        elif isinstance(self.claim_aliases, OIDCTestResultClaimAliasesType0):
            claim_aliases = self.claim_aliases.to_dict()
        else:
            claim_aliases = self.claim_aliases

        end_session_endpoint_supported = self.end_session_endpoint_supported

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "success": success,
                "message": message,
            }
        )
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if claims_supported is not UNSET:
            field_dict["claims_supported"] = claims_supported
        if claim_aliases is not UNSET:
            field_dict["claim_aliases"] = claim_aliases
        if end_session_endpoint_supported is not UNSET:
            field_dict["end_session_endpoint_supported"] = end_session_endpoint_supported

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.oidc_test_result_claim_aliases_type_0 import OIDCTestResultClaimAliasesType0
        from ..models.oidc_test_result_metadata_type_0 import OIDCTestResultMetadataType0

        d = dict(src_dict)
        success = d.pop("success")

        message = d.pop("message")

        def _parse_metadata(data: object) -> None | OIDCTestResultMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = OIDCTestResultMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OIDCTestResultMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        def _parse_claims_supported(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                claims_supported_type_0 = cast(list[str], data)

                return claims_supported_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        claims_supported = _parse_claims_supported(d.pop("claims_supported", UNSET))

        def _parse_claim_aliases(data: object) -> None | OIDCTestResultClaimAliasesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                claim_aliases_type_0 = OIDCTestResultClaimAliasesType0.from_dict(data)

                return claim_aliases_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OIDCTestResultClaimAliasesType0 | Unset, data)

        claim_aliases = _parse_claim_aliases(d.pop("claim_aliases", UNSET))

        end_session_endpoint_supported = d.pop("end_session_endpoint_supported", UNSET)

        oidc_test_result = cls(
            success=success,
            message=message,
            metadata=metadata,
            claims_supported=claims_supported,
            claim_aliases=claim_aliases,
            end_session_endpoint_supported=end_session_endpoint_supported,
        )

        return oidc_test_result
