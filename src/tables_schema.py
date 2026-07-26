from pydantic import BaseModel, ConfigDict, Field

# Classe de base réutilisable avec détection dynamique de nouvelles colonnes (extra='allow')
class BaseIGDBSchema(BaseModel):
    model_config = ConfigDict(extra='allow', populate_by_name=True)


# 1. Endpoint: /games
class GameSchema(BaseIGDBSchema):
    id: int
    name: str
    slug: str | None = None
    summary: str | None = None
    storyline: str | None = None
    
    # Timestamps système 
    created_at: int | None = None
    updated_at: int | None = None
    first_release_date: int | None = Field(default=None, alias="first_release_date")
    
    # Métriques d'évaluation et Popularité (Nouveau 2024+ PopScore / Primitives)
    rating: float | None = None
    rating_count: int | None = None
    aggregated_rating: float | None = None
    aggregated_rating_count: int | None = None
    total_rating: float | None = None
    total_rating_count: int | None = None
    hypes: int | None = None
    
    # Classification et Enums récents
    game_type: int | None = None      
    game_status: int | None = None    
    
    # Clés d'associations / Relations (IDs vers les autres tables)
    genres: list[int] = Field(default_factory=list)
    platforms: list[int] = Field(default_factory=list)
    involved_companies: list[int] = Field(default_factory=list)
    release_dates: list[int] = Field(default_factory=list)
    game_modes: list[int] = Field(default_factory=list)
    themes: list[int] = Field(default_factory=list)
    collections: list[int] = Field(default_factory=list) 
    
    # Hiérarchie et metadata
    parent_game: int | None = None
    version_parent: int | None = None
    version_title: str | None = None
    checksum: str | None = None


# 2. Endpoint: /release_dates
class ReleaseDateSchema(BaseIGDBSchema):
    id: int
    game: int | None = None
    platform: int | None = None
    date: int | None = None           # Timestamp Unix
    human: str | None = None          # Ex: "2026-Q3" ou "Dec 31, 2026"
    y: int | None = None              # Année de sortie (e.g. 2026)
    m: int | None = None              # Mois (1-12)
    region: int | None = None         # Region Enum (Europe, US, JP...)
    status: int | None = None         # Release Date Status Enum

    created_at: int | None = None
    updated_at: int | None = None
    checksum: str | None = None


# 3. Endpoint: /genres
class GenreSchema(BaseIGDBSchema):
    id: int
    name: str
    slug: str | None = None

    created_at: int | None = None
    updated_at: int | None = None
    checksum: str | None = None


# 4. Endpoint: /platforms
class PlatformSchema(BaseIGDBSchema):
    id: int
    name: str
    slug: str | None = None
    abbreviation: str | None = None
    alternative_name: str | None = None
    generation: int | None = None
    platform_family: int | None = None  # ID de la famille (PlayStation, Xbox, Nintendo)
    
    created_at: int | None = None
    updated_at: int | None = None
    checksum: str | None = None


# 5. Endpoint: /companies
class CompanySchema(BaseIGDBSchema):
    id: int
    name: str
    slug: str | None = None
    description: str | None = None
    country: int | None = None            # Code pays ISO / ID
    parent: int | None = None             # ID de la maison mère si filiale
    changed_company_id: int | None = None # Historique de restructuration ou rachat
    
    created_at: int | None = None
    updated_at: int | None = None
    checksum: str | None = None



