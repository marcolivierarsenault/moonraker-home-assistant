/* Shared G-code toolpath parser core.
 * Exposed as `MoonrakerToolpathParse` so the same code runs in the panel
 * (window), the parsing worker (self), and the Node test harness (vm). */
(function (root) {
  "use strict";

  const MAX_TOOLPATH_SEGMENTS = 28000;

  function createParseState(stride) {
    return {
      xyzAbsolute: true,
      eAbsolute: true,
      unit: 1,
      position: { x: 0, y: 0, z: 0, e: 0 },
      extrusions: 0,
      sampleStride: stride || 1,
      feedrate: 0,
      simSeconds: 0,
      layerTimes: new Map(),
    };
  }

  function createBounds() {
    return {
      minX: Infinity,
      maxX: -Infinity,
      minY: Infinity,
      maxY: -Infinity,
      minZ: Infinity,
      maxZ: -Infinity,
    };
  }

  function parseGcodeLine(line, state, fraction, stride) {
    let clean = line
      .replace(/\([^)]*\)/g, "")
      .split(";")[0]
      .trim()
      .toUpperCase();
    clean = clean.replace(/^N\d+\s*/, "");
    if (!clean) return null;
    if (/\bG90\b/.test(clean)) state.xyzAbsolute = true;
    if (/\bG91\b/.test(clean)) state.xyzAbsolute = false;
    if (/\bM82\b/.test(clean)) state.eAbsolute = true;
    if (/\bM83\b/.test(clean)) state.eAbsolute = false;
    if (/\bG20\b/.test(clean)) state.unit = 25.4;
    if (/\bG21\b/.test(clean)) state.unit = 1;

    const words = {};
    for (const match of clean.matchAll(
      /([XYZEFPS])\s*(-?(?:\d+\.?\d*|\.\d+))/g
    ))
      words[match[1]] = Number(match[2]);
    if (/\bG92\b/.test(clean)) {
      for (const axis of ["X", "Y", "Z"])
        if (words[axis] != null)
          state.position[axis.toLowerCase()] = words[axis] * state.unit;
      if (words.E != null) state.position.e = words.E * state.unit;
      return null;
    }
    if (/\bG4\b/.test(clean)) {
      const dwellMs =
        words.P != null ? words.P : words.S != null ? words.S * 1000 : 0;
      if (dwellMs > 0)
        state.simSeconds = (state.simSeconds || 0) + dwellMs / 1000;
      return null;
    }
    const command = clean.match(/(?:^|\s)(G0?0|G0?1|G0?2|G0?3)\b/);
    if (!command) return null;

    const previous = { ...state.position };
    const next = { ...state.position };
    for (const axis of ["X", "Y", "Z"]) {
      const key = axis.toLowerCase();
      if (words[axis] != null)
        next[key] = state.xyzAbsolute
          ? words[axis] * state.unit
          : previous[key] + words[axis] * state.unit;
    }
    let extrusionDelta = 0;
    if (words.E != null) {
      const extrusion = words.E * state.unit;
      next.e = state.eAbsolute ? extrusion : previous.e + extrusion;
      extrusionDelta = state.eAbsolute ? next.e - previous.e : extrusion;
    }
    if (words.F != null) state.feedrate = (words.F * state.unit) / 60;
    state.position = next;
    const distance = Math.hypot(
      next.x - previous.x,
      next.y - previous.y,
      next.z - previous.z
    );
    const moveDistance = Math.hypot(distance, next.e - previous.e);
    if (moveDistance > 0) {
      // Distance/feedrate plus a short-move accel penalty approximates move time.
      const speed = state.feedrate || 20;
      const seconds = Math.max(
        moveDistance / speed,
        Math.sqrt((2 * moveDistance) / 2500)
      );
      state.simSeconds = (state.simSeconds || 0) + seconds;
      if (!state.layerTimes) state.layerTimes = new Map();
      const zKey = Number(next.z.toFixed(2));
      state.layerTimes.set(zKey, (state.layerTimes.get(zKey) || 0) + seconds);
    }
    if (extrusionDelta <= 0.0005 || distance <= 0.0001) return null;
    state.extrusions += 1;
    const sampleStride = state.sampleStride || stride || 1;
    if (state.extrusions % sampleStride !== 0) return null;
    return {
      a: [previous.x, previous.y, previous.z],
      b: [next.x, next.y, next.z],
      fraction,
      extrusionIndex: state.extrusions,
    };
  }

  function addToolpathSegment(segments, bounds, segment, state) {
    if (segments.length >= MAX_TOOLPATH_SEGMENTS) {
      state.sampleStride = (state.sampleStride || 1) * 2;
      let kept = 0;
      for (const existing of segments) {
        if (existing.extrusionIndex % state.sampleStride === 0) {
          segments[kept++] = existing;
        }
      }
      segments.length = kept;
    }
    if (segment.extrusionIndex % (state.sampleStride || 1) !== 0) return;
    segments.push(segment);
    for (const point of [segment.a, segment.b]) {
      bounds.minX = Math.min(bounds.minX, point[0]);
      bounds.maxX = Math.max(bounds.maxX, point[0]);
      bounds.minY = Math.min(bounds.minY, point[1]);
      bounds.maxY = Math.max(bounds.maxY, point[1]);
      bounds.minZ = Math.min(bounds.minZ, point[2]);
      bounds.maxZ = Math.max(bounds.maxZ, point[2]);
    }
  }

  function normalizeBounds(bounds) {
    if (!Number.isFinite(bounds.minX)) return null;
    if (bounds.maxX - bounds.minX < 1) {
      bounds.minX -= 0.5;
      bounds.maxX += 0.5;
    }
    if (bounds.maxY - bounds.minY < 1) {
      bounds.minY -= 0.5;
      bounds.maxY += 0.5;
    }
    if (bounds.maxZ - bounds.minZ < 1) {
      bounds.minZ = Math.min(0, bounds.minZ);
      bounds.maxZ += 0.5;
    }
    return bounds;
  }

  root.MoonrakerToolpathParse = {
    MAX_TOOLPATH_SEGMENTS,
    createParseState,
    createBounds,
    parseGcodeLine,
    addToolpathSegment,
    normalizeBounds,
  };
})(typeof self !== "undefined" ? self : globalThis);
