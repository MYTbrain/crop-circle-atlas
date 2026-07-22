# Data and image rights

The MIT license covers this repository’s software. It does not relicense
third-party catalogs, reports, diagrams, or photographs.

- Public tables retain source URLs, retrieval records, hashes, and rights
  status. They do not grant rights to the underlying source material.
- `COMBINED.pdf` is a user-supplied local source and is not copied into this
  repository. Its SHA-256 is recorded in `data/build_summary.json`.
- ICCRA’s 681 non-navigation image references are inventoried and may be cached
  privately for research, but every item is `not_cleared` for public
  redistribution. The automated straight-component pass reads 669 available
  hosted images from that private cache and publishes metadata only: source URL,
  SHA-256, coverage status, diagnostics, and an unvalidated image-space review
  axis. It emits no source pixels, thumbnails, contact sheets, or derived images.
  The public atlas records source links rather than bundling the pixels.
- The global publisher pass enumerates 7,398 unique Crop Circle Center,
  Crop Circle Connector, and DCCA image URLs. Their pixels were not fetched,
  copied, or redistributed; the public catalog marks the links unverified and
  rights-gated. Missing permission fails closed to a source-record link.
- Eleven Diessenhofen/Commons report-image relationships are open-license. The
  one mapped frame is attributed to Hansueli Krapf under CC BY-SA 3.0 and loads
  from Wikimedia Commons only after explicit user action; no pixels are
  packaged in the repository or KMZ.
- The map's registered-source-photo layer is opt-in. After a user explicitly
  asks to show it, the browser requests the photograph directly from its remote
  source and draws it with registration metadata stored by the atlas. The image
  is off by default and is not proxied through this repository. The KML/KMZ
  carries the same disabled remote URL and corner metadata, but packages no
  photograph. Browser or linked display does not grant a reuse license, and the
  source may decline or block the request.
- A local image chosen in the registration lab is not uploaded. A public KML or
  KMZ overlay requires explicit permission, public-domain status, or an open
  license whose name and evidence are recorded and verified.
- The current public KML/KMZ contains zero packaged image files and thirteen
  off-by-default, provisional GroundOverlays that link directly to the source
  host. Those are not pixel redistribution or publication authorization. An
  authorized future packaged GroundOverlay must carry the rights holder/creator,
  license, proof reference, and source URL inside the KML as well as in the
  asset registry.
- GeoNames data is CC BY 4.0. OpenStreetMap data is ODbL. Esri imagery is
  displayed with provider attribution and is not repackaged by this project.

Before publishing any registered aerial image, confirm the rights holder,
license or written permission, explicit proof reference, permitted use, image
hash, reviewer, and review date in the registration/asset record. A rights label
without proof is not sufficient for combined-KMZ publication.

Official USGS or USDA imagery used as positional evidence must retain its
collection identifier, acquisition date, provider, access URL, and the
item-specific use/rights statement. A general assumption that government-hosted
imagery is public domain is not a substitute for checking the selected item.
Google Earth is used only for manual historical-imagery verification; its
basemap pixels are not scraped, downloaded into this repository, or
redistributed as atlas assets.
