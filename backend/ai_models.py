"""Shared capability checks for Mistral model IDs and aliases."""


def is_glm_model(model: str) -> bool:
    return model.strip().lower() in {"zai-glm-5-3", "zai-glm-latest"}
