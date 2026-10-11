# Morocco site refresh

The Morocco presentation is isolated in `static/css/morocco-layout.css`. Existing
content and production images remain in place. Demo data and local image URLs live
only in the ignored `tmp/preview.sqlite3` database; they must not be published.

## Booking calendar

One independent guide serves all Morocco tours. Pending and confirmed reservations
block the inclusive date range for every traveler, including the same customer.
A trip ending on the 10th allows the next departure on the 11th. Rejected,
cancelled and completed reservations do not block the calendar. New requests do
not cancel previous reservations. The existing five-night limit is unchanged.

Migration `core.0031_guidecalendar` creates the shared lock row. The availability
check and save run under this lock on MySQL/PostgreSQL, including Django admin
changes. The browser calendar is advisory; persistence rechecks availability.

Apply migrations before serving the updated booking code:

```powershell
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py test apps.core.test_seo apps.reservations.tests
```

The repository's Render start command already runs migrations. Tests use Django's
separate test database; the concurrent-request test requires a database supporting
`SELECT FOR UPDATE` and is skipped on SQLite.

## SEO

`MOROCCO_SITE_URL` defaults to `https://basmamoroccoexperience.com`. Set it to the
preferred public origin if the domain changes. Canonical tags, social URLs and the
Morocco sitemap use this same origin, without country prefixes or query strings.
Explicit country prefixes still work; the Morocco domain otherwise takes priority
over a country stored in a previous session.

Pages have individual titles, descriptions and social metadata. Public tour and
article pages include structured data derived from their content. The provider is
described as a person, not a travel agency; ratings, credentials and authors are
not invented. Login, registration, filtered listings, demo slugs and local previews
are excluded from indexing. The sitemap uses tour slugs; numeric legacy links
redirect permanently to them.

Reference: [Google canonical URL guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls),
[title guidance](https://developers.google.com/search/docs/appearance/title-link), and
[article structured data](https://developers.google.com/search/docs/appearance/structured-data/article).
