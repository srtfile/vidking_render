# VidKing Stream Extractor

A FastAPI web service that extracts m3u8/mpd stream URLs from vidking.net. Deployable to [Render](https://render.com) directly from GitHub.

## Deploy to Render

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New → Web Service**.
3. Connect your GitHub repo.
4. Render will auto-detect `render.yaml` and configure everything.
5. Click **Deploy**.

## API Usage

### Health check
```
GET /
```

### Extract stream URL
```
GET /extract?tmdb=76479&type=tv&season=5&episode=8
GET /extract?tmdb=550&type=movie
GET /extract?url=https://www.vidking.net/embed/tv/76479/5/8/
```

### Query parameters

| Param | Default | Description |
|---|---|---|
| `tmdb` | — | TMDB ID |
| `type` | `tv` | `tv` or `movie` |
| `season` | `1` | Season number (TV only) |
| `episode` | `1` | Episode number (TV only) |
| `url` | — | Full embed URL (overrides tmdb) |
| `playwright_only` | `false` | Skip direct API, use browser |
| `timeout` | `45` | Playwright timeout in seconds |

### Example response
```json
{
  "embed_url": "https://www.vidking.net/embed/tv/76479/5/8/",
  "count": 1,
  "urls": [
    "https://cdn.example.com/stream/index.m3u8"
  ]
}
```
