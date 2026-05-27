from bot.services.integrations.base import CalendarProvider


class IntegrationRegistry:
    def __init__(self) -> None:
        self._calendars: dict[str, CalendarProvider] = {}

    def register_calendar(self, name: str, provider: CalendarProvider) -> None:
        self._calendars[name] = provider

    def get_calendar(self, provider_name: str) -> CalendarProvider:
        provider = self._calendars.get(provider_name)
        if provider is None:
            raise KeyError(f"Calendar provider '{provider_name}' is not registered")
        return provider

    def has_calendar(self, provider_name: str) -> bool:
        return provider_name in self._calendars


registry = IntegrationRegistry()
