from dataclasses import dataclass

from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, DictConfig, OmegaConf

from .data import DataConfig


@dataclass
class AppConfig:
    data: DataConfig = MISSING


cs = ConfigStore.instance()
cs.store(name="app_config", node=AppConfig)


def load_app_config() -> AppConfig:
    from vnstock_forecast.config import load_config

    cfg = load_config()
    return OmegaConf.to_object(cfg)


def to_app_config(cfg: DictConfig) -> AppConfig:
    return OmegaConf.to_object(cfg)
