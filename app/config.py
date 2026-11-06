import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "bormoclass-super-secret-key-change-in-production-min32chars"
    COOKIE_DOMAIN: str = ""
    COOKIE_NAME: str = "pb_pass"
    PORT: int = 8010
    DB_PATH: str = "bormoclass.db"
    BORMOCLASS_DOMAIN: str = "localhost"

    # СанПиН 1.2.3685-21 нормы непрерывной работы с экраном (в минутах)
    SANPIN_SCREEN_LIMITS: dict = {
        1: 20,
        2: 20,
        3: 25,
        4: 25,
        5: 30,
        6: 30,
        7: 30,
        8: 30,
        9: 30,
        10: 35,
        11: 35
    }

settings = Settings()
