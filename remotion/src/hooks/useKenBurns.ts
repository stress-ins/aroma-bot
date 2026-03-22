import { interpolate, useCurrentFrame } from "remotion";

const KB_SCALE = 1.2;

interface KenBurnsResult {
  scale: number;
  translateX: number;
  translateY: number;
}

/**
 * Ken Burns hook — replicates the 4 motion patterns from video_composer.py _kb_filter().
 *
 * Motion types:
 * 0 — Zoom in (center): scale 1.0 → 1.2
 * 1 — Pan left to right at mid-zoom
 * 2 — Zoom out (center): scale 1.2 → 1.0
 * 3 — Pan right to left at mid-zoom
 */
export function useKenBurns(
  motionType: number,
  startFrame: number,
  durationFrames: number
): KenBurnsResult {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;
  const progress = interpolate(localFrame, [0, durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const motion = motionType % 4;
  const zMin = 1.0;
  const zMax = KB_SCALE;
  const zMid = (zMin + zMax) / 2;

  let scale: number;
  let translateX = 0;
  let translateY = 0;

  switch (motion) {
    case 0:
      // Zoom in from center
      scale = interpolate(progress, [0, 1], [zMin, zMax]);
      break;
    case 1:
      // Pan left to right at mid-zoom
      scale = zMid;
      // Max pan offset as percentage of image dimension
      translateX = interpolate(progress, [0, 1], [-5, 5]);
      break;
    case 2:
      // Zoom out from center
      scale = interpolate(progress, [0, 1], [zMax, zMin]);
      break;
    case 3:
      // Pan right to left at mid-zoom
      scale = zMid;
      translateX = interpolate(progress, [0, 1], [5, -5]);
      break;
    default:
      scale = zMin;
  }

  return { scale, translateX, translateY };
}
