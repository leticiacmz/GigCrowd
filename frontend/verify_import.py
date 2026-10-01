"""Re-verify the Spotify -> Songkick artist import round-trip still works."""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "null")
        except Exception:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


form = urllib.parse.urlencode(
    {"username": "authtest@example.com", "password": "AuthTest123!"}
).encode()
req = urllib.request.Request(BASE + "/auth/login", data=form, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")
with urllib.request.urlopen(req, timeout=30) as r:
    token = json.loads(r.read().decode())["access_token"]
print("auth: ok")

st, res = call("GET", "/artists/search?q=" + urllib.parse.quote("arctic monkeys"))
print("songkick search:", st, "->", len(res) if isinstance(res, list) else res)
if isinstance(res, list) and res:
    print("  first:", json.dumps(res[0])[:200])

st, res = call("GET", "/artists/search?q=" + urllib.parse.quote("arctic monkeys") + "&provider=spotify")
print("spotify search:", st)
cands = res if isinstance(res, list) else (res or {}).get("artists", (res or {}).get("results", []))
print("  candidates:", len(cands))
if not isinstance(cands, list):
    print("  raw:", str(res)[:300])
else:
    print("  first:", json.dumps(cands[0])[:260])

    sp_id = cands[0].get("provider_artist_id") or cands[0].get("spotify_id")
    sp_image = cands[0].get("image") or cands[0].get("image_url")
    print("  spotify id sent:", sp_id)

    st, imported = call(
        "POST",
        "/artists/import",
        {
            "provider": "spotify",
            "provider_artist_id": sp_id,
            "artist_data": cands[0],
            "image": sp_image,
        },
        token=token,
    )
    print("import(spotify):", st)
    print("  body:", json.dumps(imported)[:400] if isinstance(imported, (dict, list)) else str(imported)[:400])

    if st in (200, 201) and isinstance(imported, dict):
        art = imported.get("artist", imported)
        slug = art.get("slug")
        songkick_id = art.get("songkick_id") or art.get("id")
        print("  canonical slug :", slug)
        print("  songkick id    :", songkick_id)
        print("  provider fields:", {k: v for k, v in art.items() if "provider" in k or "spotify" in k})
        print("  image kept     :", bool(art.get("image")), str(art.get("image"))[:80])
        st2, detail = call("GET", "/artists/" + str(slug))
        print("  refetch status :", st2)
        print("  refetch image  :", (detail or {}).get("image") if isinstance(detail, dict) else detail)

# A name Songkick cannot resolve must fail loudly rather than import a
# different artist or invent IDs.
st, bad = call(
    "POST",
    "/artists/import",
    {
        "provider": "spotify",
        "provider_artist_id": "0notarealid0000000000",
        "artist_data": {"name": "Zzqx Nonexistent Band 9931"},
        "image": None,
    },
    token=token,
)
print("import(unresolvable):", st, str(bad)[:220])