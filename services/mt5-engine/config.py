from pydantic import BaseModel
import os


class Settings(BaseModel):
    supabase_url: str
    supabase_service_role_key: str
    mt5_terminal_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    mt5_account_label: str = "Pepperstone Demo"
    expected_broker: str = "Pepperstone"
    require_demo_account: bool = True
    telemetry_interval_seconds: int = 5


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
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
    )
