from app.domain.artist import Artist


class ArtistDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Artist:

        return Artist(
            id=str(document["_id"]),

            name=document["name"],

            normalized_name=document["normalized_name"],

            slug=document["slug"],

            external_ids=document.get(
                "external_ids",
                {},
            ),

            followers=document.get(
                "followers"
            ),

            image=document.get(
                "image"
            ),

            genres=document.get(
                "genres",
                [],
            ),

            popularity=document.get(
                "popularity"
            ),

            verified=document.get(
                "verified",
                False,
            ),
        )

    