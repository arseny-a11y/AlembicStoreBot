from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DB_NAME: str = 'database/database.db'
    TOKEN: str
    ADMIN_IDS: list[int]
    CRYPTO_PAY_TOKEN: str
    OPENROUTER_API_KEY: str

    CHANNEL_ID: int
    CHANNEL_URL: str

    CHANNEL_ID_REVIEW: int
    CHANNEL_URL_REVIEW: str

    @property
    def DATABASE_URL_aiosqlite(self) -> str:
        return f'sqlite+aiosqlite:///{self.DB_NAME}'

    @property
    def DATABASE_URL_sqlite(self) -> str:
        return f'sqlite:///{self.DB_NAME}'
 
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()