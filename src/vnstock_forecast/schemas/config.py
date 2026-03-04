from dataclasses import dataclass

from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, OmegaConf

from .data import DataConfig


@dataclass
class AppConfig:
    data: DataConfig = MISSING


cs = ConfigStore.instance()
cs.store(name="app_config", node=AppConfig)


def load_app_config() -> AppConfig:
    from vnstock_forecast.utils.config_utils import load_config

    cfg = load_config()
    return OmegaConf.to_object(cfg)
