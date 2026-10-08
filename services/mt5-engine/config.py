from pydantic import BaseModel, ConfigDict, Field
import os
from pathlib import Path
from dotenv import load_dotenv


class Settings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    supabase_url: str
    supabase_service_role_key: str
    mt5_terminal_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    mt5_account_label: str = "Pepperstone Demo"
    expected_broker: str = "Pepperstone"
    require_demo_account: bool = True
    telemetry_interval_seconds: int = Field(default=5, ge=1, le=60)
    shadow_analysis_enabled: bool = True
    max_tick_age_seconds: int = Field(default=60, ge=1, le=300)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False, interpolate=False)
    return Settings(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        mt5_terminal_path=os.environ["MT5_TERMINAL_PATH"],
        mt5_login=int(os.environ["MT5_LOGIN"]),
        mt5_password=os.environ["MT5_PASSWORD"],
        mt5_server=os.environ["MT5_SERVER"],
        mt5_account_label=os.getenv("MT5_ACCOUNT_LABEL", "Pepperstone Demo"),
        expected_broker=os.getenv("EXPECTED_BROKER", "Pepperstone"),
        require_demo_account=_env_bool("REQUIRE_DEMO_ACCOUNT", True),
        telemetry_interval_seconds=int(os.getenv("TELEMETRY_INTERVAL_SECONDS", "5")),
        shadow_analysis_enabled=_env_bool('SHADOW_ANALYSIS_ENABLED', True),
        max_tick_age_seconds=int(os.getenv('MAX_TICK_AGE_SECONDS', '60')),
    )
