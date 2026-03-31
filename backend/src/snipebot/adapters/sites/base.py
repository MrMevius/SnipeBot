from abc import ABC, abstractmethod


class SiteAdapter(ABC):
    @abstractmethod
    def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_price(self, url: str) -> float:
        raise NotImplementedError
