from app.core.logger import get_logger
from typing import Optional

logger = get_logger("artist_matching")


class ArtistMatchingService:
    @staticmethod
    def select_best_artist(query: str, search_results: list) -> Optional[dict]:
        """
        Select the best artist match from Songkick search results.
        
        Prioritizes:
        1. Exact name match with is_valid=true and is_active=true
        2. Normalized name match with validity/active status
        3. Highest score among valid/active artists
        4. Most events as tiebreaker
        5. Highest popularity as final tiebreaker
        
        Returns the selected artist document or None if no valid match found.
        """
        if not search_results:
            logger.warning(f"No search results for query: {query}")
            return None
        
        # Filter to valid and active artists
        # Score is at result level, not in document
        valid_candidates = [
            result for result in search_results
            if result.get("document", {}).get("is_valid", False) 
            and result.get("document", {}).get("is_active", False)
        ]
        
        if not valid_candidates:
            logger.warning(f"No valid/active artists found for: {query}")
            return None
        
        # Try exact name match first (case-insensitive)
        query_normalized = query.lower().strip()
        for result in valid_candidates:
            document = result.get("document", {})
            name_exact = document.get("name_exact", "").lower().strip()
            if name_exact == query_normalized:
                logger.info(f"Exact match found: {document.get('name')}")
                return document
        
        # Fall back to highest score (score is at result level)
        best_result = max(valid_candidates, key=lambda x: (
            x.get("score", 0),
            x.get("document", {}).get("number_of_events", 0),
            x.get("document", {}).get("popularity", 0)
        ))
        
        best_document = best_result.get("document", {})
        logger.info(f"Best match by score: {best_document.get('name')} "
                   f"(score: {best_result.get('score')}, "
                   f"events: {best_document.get('number_of_events')})")
        
        return best_document
