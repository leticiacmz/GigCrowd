from app.repositories.base import BaseRepository


class VenueRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "venues")