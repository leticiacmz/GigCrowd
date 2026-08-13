import pytest
from app.services.artist_matching_service import ArtistMatchingService


def test_select_best_artist_exact_match():
    """Test exact name match selection"""
    query = "Demi Lovato"
    search_results = [
        {
            "id": "Artist976211",
            "score": 120.11092,
            "document": {
                "id": "Artist976211",
                "name": "Demi Lovato",
                "name_exact": "Demi Lovato",
                "is_valid": True,
                "is_active": True,
                "number_of_events": 531,
                "popularity": 0.365521
            }
        },
        {
            "id": "Artist123456",
            "score": 0.8,
            "document": {
                "id": "Artist123456",
                "name": "DEMI LOVATO TICKETS",
                "name_exact": "DEMI LOVATO TICKETS",
                "is_valid": False,
                "is_active": False,
                "number_of_events": 0,
                "popularity": 0.0
            }
        }
    ]
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is not None
    assert result["id"] == "Artist976211"
    assert result["name"] == "Demi Lovato"


def test_select_best_artist_fuzzy_match():
    """Test fuzzy match when exact not available"""
    query = "Demi Lovato"
    search_results = [
        {
            "id": "Artist123456",
            "score": 0.9,
            "document": {
                "id": "Artist123456",
                "name": "Demi Lovato Tribute",
                "name_exact": "Demi Lovato Tribute",
                "is_valid": True,
                "is_active": True,
                "number_of_events": 50,
                "popularity": 0.2
            }
        }
    ]
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is not None
    assert result["id"] == "Artist123456"


def test_select_best_artist_no_valid_candidates():
    """Test handling of no valid candidates"""
    query = "Invalid Artist"
    search_results = [
        {
            "id": "Artist123",
            "score": 0.5,
            "document": {
                "id": "Artist123",
                "name": "Invalid",
                "is_valid": False,
                "is_active": False
            }
        }
    ]
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is None


def test_select_best_artist_no_results():
    """Test handling of empty search results"""
    query = "Nonexistent Artist"
    search_results = []
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is None


def test_select_best_artist_score_tiebreaker():
    """Test score-based tiebreaker with events and popularity"""
    query = "Test Artist"
    search_results = [
        {
            "id": "Artist1",
            "score": 0.8,
            "document": {
                "id": "Artist1",
                "name": "Test Artist A",
                "name_exact": "Test Artist A",
                "is_valid": True,
                "is_active": True,
                "number_of_events": 10,
                "popularity": 0.5
            }
        },
        {
            "id": "Artist2",
            "score": 0.8,
            "document": {
                "id": "Artist2",
                "name": "Test Artist B",
                "name_exact": "Test Artist B",
                "is_valid": True,
                "is_active": True,
                "number_of_events": 20,
                "popularity": 0.6
            }
        }
    ]
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is not None
    # Artist2 should win due to higher events and popularity with same score
    assert result["id"] == "Artist2"


def test_select_best_artist_case_insensitive_match():
    """Test case-insensitive exact match"""
    query = "demi lovato"
    search_results = [
        {
            "id": "Artist976211",
            "score": 120.11092,
            "document": {
                "id": "Artist976211",
                "name": "Demi Lovato",
                "name_exact": "Demi Lovato",
                "is_valid": True,
                "is_active": True,
                "number_of_events": 531,
                "popularity": 0.365521
            }
        }
    ]
    
    result = ArtistMatchingService.select_best_artist(query, search_results)
    
    assert result is not None
    assert result["id"] == "Artist976211"
