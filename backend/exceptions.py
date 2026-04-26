"""Custom exception types for all external service failures."""


class ERCOTFetchError(Exception):
    """Raised when fetching data from ERCOT via gridstatus fails."""
    pass


class WeatherFetchError(Exception):
    """Raised when fetching weather data from Open-Meteo fails."""
    pass


class SupabaseWriteError(Exception):
    """Raised when writing to Supabase fails."""
    pass


class SupabaseReadError(Exception):
    """Raised when reading from Supabase fails."""
    pass


class ExplainerError(Exception):
    """Raised when the Claude API explainer call fails."""
    pass
