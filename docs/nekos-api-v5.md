# Nekos API v5 integration

RemGodCatcher uses the current `https://api.nekosapi.com/v5` API.

- Image search: `GET /images`
- Tag autocomplete: `GET /tags`
- Ratings: `safe`, `suggestive`, `borderline`, `explicit`
- Up to five tags and five artists, encoded as repeated query parameters
- Pagination uses `limit` (1–100) and `offset`
- `429`, malformed JSON, and transient failures use bounded retries
- Artist, rating, and tag metadata are saved in the Gallery

The UI treats Amount `0` as unlimited mode and requires confirmation. The worker also
uses a 200-item cap per run in unlimited mode to avoid an accidental unbounded job.

Official project and API documentation: https://github.com/Nekos-API/Nekos-API
