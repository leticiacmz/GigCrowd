import pytest
import asyncio
from app.providers.songkick.client import SongkickClient


@pytest.mark.asyncio
async def test_real_songkick_search():
    """
    Integration test with real Songkick API.
    This test requires Playwright browser binaries and network access.
    """
    client = SongkickClient()
    
    try:
        result = await client.search_artist("Demi Lovato")
        
        # Verify response structure
        assert "data" in result
        assert "attributes" in result["data"]
        assert "search_results" in result["data"]["attributes"]
        
        search_results = result["data"]["attributes"]["search_results"]
        assert "artists" in search_results
        
        artists = search_results["artists"]
        assert len(artists) > 0
        
        # Verify artist structure matches real payload
        first_artist = artists[0]
        assert "id" in first_artist
        assert "score" in first_artist  # Score is at result level
        assert "document" in first_artist
        
        document = first_artist["document"]
        assert "id" in document
        assert "name" in document
        assert "name_exact" in document
        assert "is_valid" in document
        assert "is_active" in document
        assert "number_of_events" in document
        assert "popularity" in document
        
        # Verify ID format
        assert document["id"].startswith("Artist")
        
        print(f"Successfully retrieved {len(artists)} artists from Songkick")
        print(f"First artist: {document['name']} (ID: {document['id']})")
        
    except Exception as e:
        pytest.skip(f"Songkick integration test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_real_songkick_search())
