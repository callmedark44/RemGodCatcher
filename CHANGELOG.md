# Changelog

## Unreleased

- Migrate Nekos API integration from v4 to v5 with tag/artist filters and live autocomplete.
- Add worker lifecycle state, duplicate-start protection, safer unlimited-mode confirmation, and responsive UI improvements.
- Reject corrupt/non-media downloads and bound API retries.
- Fix Anime-Pictures/Pinterest imports, Sankaku directories, Rule34 credential messaging, Nekosia error handling, history clearing, and Gallery search.

## v4.3.0
- Eshuushuu worker with tag name/ID search and user ID filtering
- Tag auto-suggest: Gelbooru local DB for offline autocomplete
- NekosAPI v4: async worker with local tag DB
- Zerochan gallery-dl fallback for expanded results
- Per-worker proxy toggle in each worker tab

## v4.2.0
- Initial open-source release
- 16 platform workers (Danbooru, Gelbooru, Konachan, Yande.re, Sankaku,
  Safebooru, Zerochan, Waifu.im, Nekos.best, Nekos.life, Rule34,
  NekosAPI v4, Nekosia, Pinterest, Pixiv, Anime-Pictures.net)
- Glass-morphism web UI with dark/light themes
- Concurrent multi-tag dispatch
- Gallery with search, filter, sort
- Pixiv ugoira-to-GIF conversion
- Hydrus sidecar file support
