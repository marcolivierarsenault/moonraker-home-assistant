/* Web Worker that parses streamed G-code into toolpath segments so the
 * panel's main thread stays responsive on large files. */
importScripts("toolpath_parse.js");

const P = self.MoonrakerToolpathParse;

let state = null;
let bounds = null;
let segments = [];
let rangeStart = 0;
let rangeEnd = Infinity;
let rangeBytes = 1;
let buffer = "";
let parsedChars = 0;
let lineCount = 0;

function fractionAt(offset) {
  if (!Number.isFinite(rangeEnd)) return 0;
  return Math.max(0, Math.min((offset - rangeStart) / rangeBytes, 1));
}

function processLine(rawLine) {
  const line = rawLine.replace(/\r$/, "");
  parsedChars += line.length + 1;
  const segment = P.parseGcodeLine(
    line,
    state,
    fractionAt(parsedChars),
    state.sampleStride
  );
  if (segment && parsedChars >= rangeStart && parsedChars <= rangeEnd) {
    P.addToolpathSegment(segments, bounds, segment, state);
  }
  lineCount += 1;
}

self.onmessage = (event) => {
  const msg = event.data || {};
  if (msg.type === "start") {
    rangeStart = Number.isFinite(msg.rangeStart) ? msg.rangeStart : 0;
    rangeEnd = Number.isFinite(msg.rangeEnd) ? msg.rangeEnd : Infinity;
    rangeBytes = Number.isFinite(rangeEnd)
      ? Math.max(1, rangeEnd - rangeStart)
      : 1;
    state = P.createParseState(msg.stride || 1);
    bounds = P.createBounds();
    segments = [];
    buffer = "";
    parsedChars = 0;
    lineCount = 0;
    self.postMessage({ type: "ready" });
    return;
  }
  if (!state) return;
  if (msg.type === "text") {
    buffer += msg.text;
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const rawLine of lines) processLine(rawLine);
    self.postMessage({ type: "progress", segments: segments.length });
    return;
  }
  if (msg.type === "end") {
    if (buffer) processLine(buffer);
    if (!Number.isFinite(rangeEnd) && segments.length > 1) {
      segments.forEach((segment, index) => {
        segment.fraction = index / (segments.length - 1);
      });
    }
    self.postMessage({
      type: "done",
      segments,
      bounds,
      layerStats: [...state.layerTimes]
        .map(([z, seconds]) => ({ z, seconds }))
        .sort((a, b) => a.z - b.z),
      simSeconds: state.simSeconds || 0,
    });
  }
};
