from pydantic import BaseModel
import os

class Settings(BaseModel):
    supabase_url: str
    supabase_service_role_key: str
    mt5_terminal_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    mt5_account_label: str = "Trive Demo"


def load_settings() -> Settings:
    return Settings(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        mt5_terminal_path=os.environ["MT5_TERMINAL_PATH"],
        mt5_login=int(os.environ["MT5_LOGIN"]),
        mt5_password=os.environ["MT5_PASSWORD"],
        mt5_server=os.environ["MT5_SERVER"],
        mt5_account_label=os.getenv("MT5_ACCOUNT_LABEL", "Trive Demo"),
    )
