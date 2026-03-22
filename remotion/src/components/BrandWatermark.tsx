import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

interface BrandWatermarkProps {
  text?: string;
  position?: "top-right" | "bottom-right" | "top-left" | "bottom-left";
}

export const BrandWatermark: React.FC<BrandWatermarkProps> = ({
  text = "AROMARA",
  position = "top-right",
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Fade in at start, persist, fade out at end
  const opacity = interpolate(
    frame,
    [0, 30, durationInFrames - 30, durationInFrames],
    [0, 0.4, 0.4, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const positionStyles: React.CSSProperties = {};
  if (position.includes("top")) positionStyles.top = 60;
  if (position.includes("bottom")) positionStyles.bottom = 60;
  if (position.includes("right")) positionStyles.right = 30;
  if (position.includes("left")) positionStyles.left = 30;

  return (
    <div
      style={{
        position: "absolute",
        opacity,
        pointerEvents: "none",
        ...positionStyles,
      }}
    >
      <span
        style={{
          color: "#fff",
          fontSize: 24,
          fontFamily: "'Inter', 'Noto Sans', sans-serif",
          fontWeight: 700,
          letterSpacing: 3,
          textTransform: "uppercase",
          textShadow: "0 1px 4px rgba(0,0,0,0.5)",
        }}
      >
        {text}
      </span>
    </div>
  );
};
