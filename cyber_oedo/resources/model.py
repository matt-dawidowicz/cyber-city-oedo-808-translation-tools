"""Typed candidate-resource structures for sector-aligned payload regions."""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.game_layout import SECTOR_SIZE, bank_for_sector


@dataclass(frozen=True, slots=True, order=True)
class ResourceHeader:
    """Represent one plausible resource identifier at a sector boundary."""

    sector: int
    name: str

    def __post_init__(self) -> None:
        """Validate the non-negative sector and non-empty identifier."""

        if self.sector < 0:
            raise ValueError("resource sector must be non-negative")
        if not self.name:
            raise ValueError("resource name must not be empty")

    @property
    def offset(self) -> int:
        """Return the payload byte offset of this header."""

        return self.sector * SECTOR_SIZE

    @property
    def bank(self) -> str:
        """Return the analysis-bank label containing this header."""

        return bank_for_sector(self.sector)


@dataclass(frozen=True, slots=True)
class CandidateResourceRegion:
    """Describe a header-bounded candidate resource interval.

    The boundary is heuristic. This object does not claim that the game loader
    reads the complete interval or that any apparent padding inside it is free.
    """

    header: ResourceHeader
    end_sector: int
    boundary_source: str

    def __post_init__(self) -> None:
        """Require a positive half-open interval and named boundary source."""

        if self.end_sector <= self.header.sector:
            raise ValueError("resource end must follow its header sector")
        if not self.boundary_source:
            raise ValueError("boundary_source must not be empty")

    @property
    def start_sector(self) -> int:
        """Return the first sector in the candidate interval."""

        return self.header.sector

    @property
    def start_offset(self) -> int:
        """Return the first payload byte in the candidate interval."""

        return self.start_sector * SECTOR_SIZE

    @property
    def end_offset(self) -> int:
        """Return the exclusive payload byte end of the interval."""

        return self.end_sector * SECTOR_SIZE

    @property
    def sector_count(self) -> int:
        """Return the candidate interval length in sectors."""

        return self.end_sector - self.start_sector

    @property
    def byte_count(self) -> int:
        """Return the candidate interval length in payload bytes."""

        return self.sector_count * SECTOR_SIZE

    @property
    def bank(self) -> str:
        """Return the analysis-bank label at the resource start."""

        return self.header.bank


__all__ = ["CandidateResourceRegion", "ResourceHeader"]
