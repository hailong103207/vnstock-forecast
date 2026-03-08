from dataclasses import dataclass
from enum import Enum

from omegaconf import MISSING


class DataClient(str, Enum):
    vietstock = "vietstock"
    vietcap = "vietcap"


"""DISCORVERY CONSTANT"""


@dataclass
class DiscoverySymbolsConfig:
    vn30: list[str] = MISSING
    vnindex: list[str] = MISSING


@dataclass
class VietstockResolutionConfig:
    daily: str = MISSING
    m1: int = MISSING
    m5: int = MISSING
    m15: int = MISSING
    m30: int = MISSING
    m45: int = MISSING
    h1: int = MISSING
    h3: int = MISSING
    h4: int = MISSING


@dataclass
class DiscoveryResolutionConfig:
    vietstock: VietstockResolutionConfig = MISSING


@dataclass
class DiscoveryConfig:
    symbols: DiscoverySymbolsConfig = MISSING
    resolutions: DiscoveryResolutionConfig = MISSING


"""UPDATER CONFIG"""


@dataclass
class UpdaterConfig:
    client: DataClient = MISSING
    symbols: list[str] = MISSING
    resolutions: list[str] = MISSING
    lookback_days: int = 365


"""DATA CONFIG"""


@dataclass
class DataConfig:
    discovery: DiscoveryConfig = MISSING
    updater: UpdaterConfig = MISSING
