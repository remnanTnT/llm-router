from __future__ import annotations

from collections.abc import Iterable

from router.models import Model


class ModelRepository:
    @staticmethod
    def get_by_name(model_name: str | None) -> Model | None:
        if not model_name:
            return None
        return Model.objects.filter(model_name=model_name).first()

    @staticmethod
    def get_or_create(model_name: str) -> tuple[Model, bool]:
        return Model.objects.get_or_create(
            model_name=model_name,
            defaults={"concurrent_limit": 3, "max_tokens": 20480},
        )

    @staticmethod
    def list_all() -> list[Model]:
        return list(Model.objects.all().order_by("id"))

    @staticmethod
    def get_by_names(model_names: list[str]) -> dict[str, Model]:
        return {model.model_name: model for model in Model.objects.filter(model_name__in=model_names)}

    @staticmethod
    def get_by_ids(model_ids: Iterable[int]) -> dict[int, Model]:
        return {model.id: model for model in Model.objects.filter(id__in=list(model_ids))}

    @staticmethod
    def list_online() -> list[Model]:
        """List all models that are not deprecated (deprecation is null)."""
        return list(Model.objects.filter(deprecation__isnull=True).order_by("id"))
