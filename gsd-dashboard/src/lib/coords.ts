/**
 * Convert DOM coordinates (relative to canvas/element) to surface coordinates
 * (relative to the browser viewport being streamed).
 */
export function domToSurface(
  domX: number,
  domY: number,
  elementWidth: number,
  elementHeight: number,
  surfaceWidth: number,
  surfaceHeight: number,
): { x: number; y: number } {
  const scaleX = surfaceWidth / elementWidth;
  const scaleY = surfaceHeight / elementHeight;
  return {
    x: Math.round(domX * scaleX),
    y: Math.round(domY * scaleY),
  };
}
