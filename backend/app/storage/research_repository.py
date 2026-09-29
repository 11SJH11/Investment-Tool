"""Compatibility import for existing experiment workers; new code uses explicit ownership."""
from app.storage.research_experiment_repository import ResearchExperimentRepository

ResearchRepository = ResearchExperimentRepository
