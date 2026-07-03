from app.repositories.base import BaseRepository


class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "events")