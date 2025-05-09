import os
import uuid
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv, find_dotenv
from loguru import logger
from pydantic import computed_field, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.introspection import get_absolute_path

DOTENV = get_absolute_path(".env")


class ComfyUISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='comfyui_', env_file=DOTENV, extra="ignore")

    install_path: Path
    workspace_path: Path
    listen_port: int = Field(default=8188, description="Port to listen on.")
    listen_address: str = Field(default="localhost", description="Address to listen on.")

    @computed_field  # type: ignore
    @property
    def interpreter_path(self) -> Path:
        venv_path = self.install_path / ".venv/bin/python"
        alt_path = self.install_path / "venv/bin/python"
        return venv_path if venv_path.exists() else alt_path

    @computed_field  # type: ignore
    @property
    def main_path(self) -> Path:
        return self.install_path / "main.py"

    @computed_field  # type: ignore
    @property
    def workflows_path(self) -> Path:
        return self.workspace_path / "user" / "default" / "workflows"

    @computed_field  # type: ignore
    @property
    def models_path(self) -> Path:
        return self.workspace_path / "models"



class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='app_', env_file=DOTENV, extra="ignore")

    api_key: str
    listen_port: int = Field(default=8188, description="Port to listen on.")
    listen_address: str = Field(default="localhost", description="Address to listen on.")

    @field_validator('api_key', mode='after')
    @classmethod
    def ensure_valid_api_key(cls, value: str) -> str:
        """
        If the API key is the default value of 'GENERATE_API_KEY', generate a random key,
        overwrite the default key in the .env file, and return the new key.
        :param value:
        :return:
        """
        if value == 'GENERATE_API_KEY':
            logger.info('Default API key detected. Generating new API key and saving to .env file.')
            new_key = uuid.uuid4().hex
            # Read the existing content

            with open(DOTENV, 'r') as f:
                lines = f.readlines()

            # Replace the line with APP_API_KEY
            with open(DOTENV, 'w') as f:
                for line in lines:
                    if line.startswith('APP_API_KEY='):
                        f.write(f"APP_API_KEY={new_key}\n")
                    else:
                        f.write(line)

            return new_key
        return value

#f.write(f"API_KEY={new_key}\n")

@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    load_dotenv(find_dotenv())
    return AppSettings()

@lru_cache(maxsize=1)
def get_comfyui_settings() -> ComfyUISettings:
    load_dotenv(find_dotenv())
    return ComfyUISettings()


if __name__ == "__main__":
    print(get_comfyui_settings().model_dump())