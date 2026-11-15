import logging
from typing import Optional
import spacy
import spacy.cli
from spacy.language import Language

logger = logging.getLogger(__name__)

# Module-level singleton
_NLP_INSTANCE: Optional[Language] = None


def get_nlp() -> Language:
    """
    Returns a shared singleton instance of spaCy's en_core_web_sm model.
    Optimized for Render Free Tier (512 MB RAM limit):
    - Loaded strictly once in memory (~120 MB working set)
    - Disables lemmatizer to save RAM and initialization time
    - Auto-downloads model if missing in environment
    """
    global _NLP_INSTANCE
    if _NLP_INSTANCE is None:
        model_name = "en_core_web_sm"
        try:
            logger.info("Loading spaCy model: %s", model_name)
            # Disable lemmatizer to save memory and CPU cycles
            _NLP_INSTANCE = spacy.load(model_name, disable=["lemmatizer"])
        except OSError:
            logger.warning(
                "spaCy model '%s' not found locally. Downloading into environment...",
                model_name
            )
            spacy.cli.download(model_name)
            _NLP_INSTANCE = spacy.load(model_name, disable=["lemmatizer"])

        logger.info("spaCy model '%s' loaded successfully (singleton initialized).", model_name)

    return _NLP_INSTANCE
