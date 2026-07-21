/**
 * Opt-in projective image overlay for Leaflet.
 *
 * The module is inert on import. A remote image request begins only after an
 * overlay instance is added to a map. The image is drawn directly to a
 * tessellated canvas mesh; this module deliberately exposes no pixel or canvas
 * export API and does not request CORS-readable source pixels.
 *
 * Corner order follows the source image, not compass directions:
 * [top-left, top-right, bottom-right, bottom-left]. Each corner may be a
 * Leaflet LatLng-like object, [latitude, longitude], or an object with those
 * four named corner properties.
 */

const EPSILON = 1e-10;
const UNIT_SQUARE = Object.freeze([[0, 0], [1, 0], [1, 1], [0, 1]]);
const CORNER_NAMES = Object.freeze(["topLeft", "topRight", "bottomRight", "bottomLeft"]);
const CLASS_CACHE = new WeakMap();

function finitePoint(point, label) {
  if (!Array.isArray(point) || point.length !== 2 || point.some((value) => !Number.isFinite(value))) {
    throw new TypeError(`${label} must be a finite two-dimensional point.`);
  }
  return [Number(point[0]), Number(point[1])];
}

function signedArea(points) {
  return points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
}

function isConvexQuad(points) {
  let direction = 0;
  for (let index = 0; index < 4; index += 1) {
    const a = points[index];
    const b = points[(index + 1) % 4];
    const c = points[(index + 2) % 4];
    const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(cross) <= EPSILON) return false;
    const sign = Math.sign(cross);
    if (direction && sign !== direction) return false;
    direction = sign;
  }
  return Math.abs(signedArea(points)) > EPSILON;
}

function solveLinearSystem(matrix, vector) {
  const size = vector.length;
  const augmented = matrix.map((row, index) => [...row, vector[index]]);
  for (let column = 0; column < size; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < size; row += 1) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
    }
    if (Math.abs(augmented[pivot][column]) <= EPSILON) {
      throw new Error("Point pairs do not determine a stable projective transform.");
    }
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
    const divisor = augmented[column][column];
    for (let index = column; index <= size; index += 1) augmented[column][index] /= divisor;
    for (let row = 0; row < size; row += 1) {
      if (row === column) continue;
      const factor = augmented[row][column];
      for (let index = column; index <= size; index += 1) {
        augmented[row][index] -= factor * augmented[column][index];
      }
    }
  }
  return augmented.map((row) => row[size]);
}

/** Solve an exact homography from four source/target point pairs. */
export function solveHomography(sourcePoints, targetPoints) {
  if (!Array.isArray(sourcePoints) || !Array.isArray(targetPoints)
      || sourcePoints.length !== 4 || targetPoints.length !== 4) {
    throw new Error("A projective transform requires exactly four source and four target points.");
  }
  const source = sourcePoints.map((point, index) => finitePoint(point, `Source point ${index + 1}`));
  const target = targetPoints.map((point, index) => finitePoint(point, `Target point ${index + 1}`));
  if (!isConvexQuad(source) || !isConvexQuad(target)) {
    throw new Error("Projective corners must form ordered, non-degenerate convex quadrilaterals.");
  }
  const equations = [];
  const values = [];
  source.forEach(([x, y], index) => {
    const [u, v] = target[index];
    equations.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    values.push(u);
    equations.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    values.push(v);
  });
  return [...solveLinearSystem(equations, values), 1];
}

/** Map a two-dimensional point through a flat, row-major 3x3 homography. */
export function applyHomography(matrix, point) {
  if (!Array.isArray(matrix) || matrix.length !== 9 || matrix.some((value) => !Number.isFinite(value))) {
    throw new TypeError("Homography must be a finite, flat 3x3 matrix.");
  }
  const [x, y] = finitePoint(point, "Point");
  const denominator = matrix[6] * x + matrix[7] * y + matrix[8];
  if (!Number.isFinite(denominator) || Math.abs(denominator) <= EPSILON) {
    throw new Error("Point maps to the projective horizon.");
  }
  return [
    (matrix[0] * x + matrix[1] * y + matrix[2]) / denominator,
    (matrix[3] * x + matrix[4] * y + matrix[5]) / denominator,
  ];
}

/** Construct a homography mapping the source image's unit square to four points. */
export function homographyFromUnitSquare(targetCorners) {
  return solveHomography(UNIT_SQUARE, targetCorners);
}

function normalizeOneCorner(value, label) {
  if (Array.isArray(value)) {
    const [latitude, longitude] = finitePoint(value, label);
    return [latitude, longitude];
  }
  if (value && Number.isFinite(Number(value.lat)) && Number.isFinite(Number(value.lng))) {
    return [Number(value.lat), Number(value.lng)];
  }
  if (value && Number.isFinite(Number(value.latitude)) && Number.isFinite(Number(value.longitude))) {
    return [Number(value.latitude), Number(value.longitude)];
  }
  throw new TypeError(`${label} must be [latitude, longitude] or a LatLng-like object.`);
}

/** Normalize geodetic image corners while retaining source-image corner order. */
export function normalizeGeodeticCorners(corners) {
  const ordered = Array.isArray(corners) ? corners : CORNER_NAMES.map((name) => corners?.[name]);
  if (!Array.isArray(ordered) || ordered.length !== 4) {
    throw new Error("Four geodetic corners are required in top-left clockwise order.");
  }
  return ordered.map((corner, index) => normalizeOneCorner(corner, CORNER_NAMES[index]));
}

function affineFromTriangles(source, target) {
  const [[x0, y0], [x1, y1], [x2, y2]] = source;
  const denominator = x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1);
  if (Math.abs(denominator) <= EPSILON) return null;
  const coefficients = (values) => {
    const [v0, v1, v2] = values;
    return [
      (v0 * (y1 - y2) + v1 * (y2 - y0) + v2 * (y0 - y1)) / denominator,
      (v0 * (x2 - x1) + v1 * (x0 - x2) + v2 * (x1 - x0)) / denominator,
      (v0 * (x1 * y2 - x2 * y1) + v1 * (x2 * y0 - x0 * y2)
        + v2 * (x0 * y1 - x1 * y0)) / denominator,
    ];
  };
  const [a, c, e] = coefficients(target.map((point) => point[0]));
  const [b, d, f] = coefficients(target.map((point) => point[1]));
  return [a, b, c, d, e, f];
}

function drawTriangle(context, image, source, target, pixelRatio) {
  const affine = affineFromTriangles(source, target);
  if (!affine || affine.some((value) => !Number.isFinite(value))) return;
  context.save();
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.beginPath();
  context.moveTo(target[0][0], target[0][1]);
  context.lineTo(target[1][0], target[1][1]);
  context.lineTo(target[2][0], target[2][1]);
  context.closePath();
  context.clip();
  context.transform(...affine);
  const sourceXs = source.map((point) => point[0]);
  const sourceYs = source.map((point) => point[1]);
  const sourceLeft = Math.max(0, Math.min(...sourceXs) - 0.5);
  const sourceTop = Math.max(0, Math.min(...sourceYs) - 0.5);
  const sourceRight = Math.min(image.naturalWidth, Math.max(...sourceXs) + 0.5);
  const sourceBottom = Math.min(image.naturalHeight, Math.max(...sourceYs) + 0.5);
  const sourceWidth = sourceRight - sourceLeft;
  const sourceHeight = sourceBottom - sourceTop;
  context.drawImage(image, sourceLeft, sourceTop, sourceWidth, sourceHeight,
    sourceLeft, sourceTop, sourceWidth, sourceHeight);
  context.restore();
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function requireLeaflet(Leaflet) {
  if (!Leaflet?.Layer?.extend || !Leaflet?.DomUtil || !Leaflet?.latLng) {
    throw new Error("A Leaflet 1.x namespace is required to create the projective overlay class.");
  }
  return Leaflet;
}

/**
 * Create (and cache) a Leaflet Layer subclass for a specific Leaflet namespace.
 * The resulting class has Leaflet-standard addTo/remove/fire behavior.
 */
export function createProjectiveImageOverlayClass(Leaflet = globalThis.L) {
  const L = requireLeaflet(Leaflet);
  if (CLASS_CACHE.has(L)) return CLASS_CACHE.get(L);

  const ProjectiveImageOverlay = L.Layer.extend({
    options: {
      opacity: 0.72,
      subdivisions: 16,
      pane: "overlayPane",
      zIndex: 1,
      imageSmoothing: true,
      maxPixelRatio: 2,
      className: "leaflet-projective-image-overlay",
    },

    initialize(sourceUrl, corners, options = {}) {
      if (typeof sourceUrl !== "string" || !sourceUrl.trim()) {
        throw new TypeError("A non-empty source image URL is required.");
      }
      L.setOptions(this, options);
      this._sourceUrl = sourceUrl;
      this._cornerCoordinates = normalizeGeodeticCorners(corners);
      this._opacity = clamp(Number(this.options.opacity) || 0, 0, 1);
      this._loadGeneration = 0;
      this._redrawFrame = null;
      this._imageLoaded = false;
      this._lastRenderError = null;
    },

    onAdd(map) {
      this._map = map;
      this._canvas = L.DomUtil.create("canvas", this.options.className);
      this._canvas.setAttribute("aria-hidden", "true");
      this._canvas.style.pointerEvents = "none";
      this._canvas.style.position = "absolute";
      this._canvas.style.opacity = String(this._opacity);
      this._canvas.style.zIndex = String(this.options.zIndex);
      map.getPane(this.options.pane).appendChild(this._canvas);
      map.on("moveend zoomend viewreset resize", this._scheduleRedraw, this);
      this._scheduleRedraw();
      this._loadRemoteImage();
    },

    onRemove(map) {
      map.off("moveend zoomend viewreset resize", this._scheduleRedraw, this);
      this._loadGeneration += 1;
      if (this._redrawFrame !== null) L.Util.cancelAnimFrame(this._redrawFrame);
      this._redrawFrame = null;
      if (this._image) {
        this._image.onload = null;
        this._image.onerror = null;
        this._image.removeAttribute("src");
      }
      this._image = null;
      this._imageLoaded = false;
      if (this._canvas) L.DomUtil.remove(this._canvas);
      this._canvas = null;
      this._map = null;
    },

    getAttribution() {
      return this.options.attribution || null;
    },

    getSourceUrl() {
      return this._sourceUrl;
    },

    getCorners() {
      return this._cornerCoordinates.map((corner) => [...corner]);
    },

    getBounds() {
      return L.latLngBounds(this._cornerCoordinates.map(([lat, lng]) => L.latLng(lat, lng)));
    },

    setCorners(corners) {
      this._cornerCoordinates = normalizeGeodeticCorners(corners);
      return this.redraw();
    },

    setOpacity(opacity) {
      const numeric = Number(opacity);
      if (!Number.isFinite(numeric)) throw new TypeError("Opacity must be a finite number.");
      this._opacity = clamp(numeric, 0, 1);
      if (this._canvas) this._canvas.style.opacity = String(this._opacity);
      return this;
    },

    setZIndex(zIndex) {
      this.options.zIndex = Number(zIndex);
      if (this._canvas) this._canvas.style.zIndex = String(this.options.zIndex);
      return this;
    },

    redraw() {
      if (this._map) this._scheduleRedraw();
      return this;
    },

    _loadRemoteImage() {
      const generation = ++this._loadGeneration;
      const ImageConstructor = globalThis.Image;
      if (typeof ImageConstructor !== "function") {
        this._reportImageError(new Error("This browser does not provide an Image constructor."));
        return;
      }
      const image = new ImageConstructor();
      this._image = image;
      image.decoding = "async";
      image.onload = () => {
        if (generation !== this._loadGeneration || !this._map) return;
        this._imageLoaded = true;
        this._lastRenderError = null;
        this.fire("load", { sourceUrl: this._sourceUrl });
        this._scheduleRedraw();
      };
      image.onerror = () => {
        if (generation !== this._loadGeneration || !this._map) return;
        this._reportImageError(new Error("The remote overlay image could not be loaded."));
      };
      // Intentionally omit crossOrigin. Cross-origin pixels remain unreadable and
      // the canvas cannot be exported as a way to copy the remote source image.
      image.src = this._sourceUrl;
    },

    _reportImageError(error) {
      this._imageLoaded = false;
      if (this._canvas) this._canvas.style.visibility = "hidden";
      this.fire("imageloaderror", { error, sourceUrl: this._sourceUrl });
    },

    _scheduleRedraw() {
      if (!this._map || this._redrawFrame !== null) return;
      this._redrawFrame = L.Util.requestAnimFrame(() => {
        this._redrawFrame = null;
        this._render();
      }, this);
    },

    _render() {
      if (!this._map || !this._canvas) return;
      const size = this._map.getSize();
      const width = Math.max(0, Math.round(size.x));
      const height = Math.max(0, Math.round(size.y));
      if (!width || !height) return;
      const maximumRatio = clamp(Number(this.options.maxPixelRatio) || 1, 1, 4);
      const pixelRatio = clamp(Number(globalThis.devicePixelRatio) || 1, 1, maximumRatio);
      const layerOrigin = this._map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(this._canvas, layerOrigin);
      this._canvas.style.width = `${width}px`;
      this._canvas.style.height = `${height}px`;
      const backingWidth = Math.max(1, Math.round(width * pixelRatio));
      const backingHeight = Math.max(1, Math.round(height * pixelRatio));
      if (this._canvas.width !== backingWidth) this._canvas.width = backingWidth;
      if (this._canvas.height !== backingHeight) this._canvas.height = backingHeight;
      const context = this._canvas.getContext("2d", { alpha: true });
      if (!context) {
        this._canvas.style.visibility = "hidden";
        if (this._lastRenderError !== "Canvas 2D rendering is unavailable.") {
          this._lastRenderError = "Canvas 2D rendering is unavailable.";
          this.fire("overlayrendererror", {
            error: new Error(this._lastRenderError), sourceUrl: this._sourceUrl,
          });
        }
        return;
      }
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, backingWidth, backingHeight);
      if (!this._imageLoaded || !this._image?.naturalWidth || !this._image?.naturalHeight) return;

      try {
        const targetCorners = this._cornerCoordinates.map(([latitude, longitude]) => {
          const point = this._map.latLngToLayerPoint(L.latLng(latitude, longitude));
          return [point.x - layerOrigin.x, point.y - layerOrigin.y];
        });
        const homography = homographyFromUnitSquare(targetCorners);
        const subdivisions = Math.round(clamp(Number(this.options.subdivisions) || 16, 2, 64));
        const imageWidth = this._image.naturalWidth;
        const imageHeight = this._image.naturalHeight;
        context.imageSmoothingEnabled = Boolean(this.options.imageSmoothing);
        this._canvas.style.visibility = "visible";

        for (let row = 0; row < subdivisions; row += 1) {
          const v0 = row / subdivisions;
          const v1 = (row + 1) / subdivisions;
          for (let column = 0; column < subdivisions; column += 1) {
            const u0 = column / subdivisions;
            const u1 = (column + 1) / subdivisions;
            const sourceTopLeft = [u0 * imageWidth, v0 * imageHeight];
            const sourceTopRight = [u1 * imageWidth, v0 * imageHeight];
            const sourceBottomRight = [u1 * imageWidth, v1 * imageHeight];
            const sourceBottomLeft = [u0 * imageWidth, v1 * imageHeight];
            const targetTopLeft = applyHomography(homography, [u0, v0]);
            const targetTopRight = applyHomography(homography, [u1, v0]);
            const targetBottomRight = applyHomography(homography, [u1, v1]);
            const targetBottomLeft = applyHomography(homography, [u0, v1]);
            drawTriangle(context, this._image,
              [sourceTopLeft, sourceTopRight, sourceBottomRight],
              [targetTopLeft, targetTopRight, targetBottomRight], pixelRatio);
            drawTriangle(context, this._image,
              [sourceTopLeft, sourceBottomRight, sourceBottomLeft],
              [targetTopLeft, targetBottomRight, targetBottomLeft], pixelRatio);
          }
        }
        this._lastRenderError = null;
      } catch (error) {
        this._canvas.style.visibility = "hidden";
        if (error.message !== this._lastRenderError) {
          this._lastRenderError = error.message;
          this.fire("overlayrendererror", { error, sourceUrl: this._sourceUrl });
        }
      }
    },
  });

  CLASS_CACHE.set(L, ProjectiveImageOverlay);
  return ProjectiveImageOverlay;
}

/** Leaflet-style factory; the remote request starts when the layer is added. */
export function projectiveImageOverlay(sourceUrl, corners, options = {}, Leaflet = globalThis.L) {
  const OverlayClass = createProjectiveImageOverlayClass(Leaflet);
  return new OverlayClass(sourceUrl, corners, options);
}

/** Optionally install conventional L.ProjectiveImageOverlay/L.projectiveImageOverlay names. */
export function installProjectiveImageOverlay(Leaflet = globalThis.L) {
  const L = requireLeaflet(Leaflet);
  const OverlayClass = createProjectiveImageOverlayClass(L);
  L.ProjectiveImageOverlay = OverlayClass;
  L.projectiveImageOverlay = (sourceUrl, corners, options = {}) =>
    new OverlayClass(sourceUrl, corners, options);
  return OverlayClass;
}
