import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

interface CrossfadeTransitionProps {
  startFrame: number;
  durationFrames: number;
  children: React.ReactNode;
}

/**
 * Wraps a child component with a crossfade (opacity) transition.
 * Fades in at the start and fades out at the end.
 */
export const CrossfadeTransition: React.FC<CrossfadeTransitionProps> = ({
  startFrame,
  durationFrames,
  children,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) {
    return null;
  }

  const crossfadeDur = 15; // ~0.5s at 30fps

  const opacity = interpolate(
    localFrame,
    [0, crossfadeDur, durationFrames - crossfadeDur, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        opacity,
      }}
    >
      {children}
    </div>
  );
};
