# Search discoverability

Production canonical domain: https://gridline-motorsport.vercel.app

The Next.js web app maintains canonical page URLs and social metadata through
`apps/web/lib/seo.ts`. Its public routes are described by `app/sitemap.ts`
and `app/robots.ts`. The sitemap fetches only *active* series from the public
API; it falls back to the five core routes if the API is unavailable.

The private `/manage/[token]` page has `robots: { index: false }`. Do not
disallow `/manage/` in robots.txt: crawlers need access to read the noindex
directive. No token URLs should be linked from public pages or put in the sitemap.
Robots directives are **not** an access-control mechanism.

## After deploying

1. Verify `https://gridline-motorsport.vercel.app/robots.txt` and
   `https://gridline-motorsport.vercel.app/sitemap.xml` return 200.
2. Check the homepage HTML for the canonical link, meta description,
   Open Graph tags and the generated `og:image`.
3. Ensure `https://gridline-gamma.vercel.app` redirects to the canonical
   host. Prefer an HTTP **308 permanent redirect** rather than a temporary 307
   in Vercel Settings → Domains.
4. Add the canonical URL-prefix property in
   [Google Search Console](https://search.google.com/search-console/).
   Verify ownership using a Google-provided HTML file/meta tag (do not invent a
   verification token), then submit `sitemap.xml` and request indexing for
   the homepage.
5. Add the site to [Yandex Webmaster](https://webmaster.yandex.com/) if
   Russian-language discovery matters. Verify ownership and submit the same
   sitemap.
6. Check indexing/crawl reports after deployment. Indexing is not guaranteed
   and can take days to weeks.

The website is currently English-only. Avoid adding hreflang for languages that
do not exist. If the canonical production host changes in future, update
`SITE_URL`, the README, Vercel's redirect and webmaster properties together.
