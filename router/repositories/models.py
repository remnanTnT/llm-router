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
