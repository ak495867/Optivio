from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_id: str
    version: str
    code_revision: str
    data_manifest_hash: str
    config_hash: str
    artifact_hash: str
    signature: str = ""

    def payload(self) -> bytes:
        return json.dumps({"model_id": self.model_id, "version": self.version, "code_revision": self.code_revision, "data_manifest_hash": self.data_manifest_hash, "config_hash": self.config_hash, "artifact_hash": self.artifact_hash}, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, signing_key: bytes) -> ModelManifest:
        return ModelManifest(self.model_id, self.version, self.code_revision, self.data_manifest_hash, self.config_hash, self.artifact_hash, hmac.new(signing_key, self.payload(), hashlib.sha256).hexdigest())

    def verify(self, signing_key: bytes) -> bool:
        return bool(self.signature) and hmac.compare_digest(self.signature, hmac.new(signing_key, self.payload(), hashlib.sha256).hexdigest())


def hash_artifact(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
