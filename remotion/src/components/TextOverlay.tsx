import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TextAnimation } from "../types";

interface TextOverlayProps {
  text: string;
  animation: TextAnimation;
  startFrame: number;
  durationFrames: number;
  /** Font size in px (default 42, matching FFmpeg drawtext) */
  fontSize?: number;
}

export const TextOverlay: React.FC<TextOverlayProps> = ({
  text,
  animation,
  startFrame,
  durationFrames,
  fontSize = 42,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - startFrame;

  if (!text || localFrame < 0 || localFrame > durationFrames) {
    return null;
  }

  const fadeDurFrames = Math.round(0.5 * fps); // 0.5s fade matching FFmpeg

  // Base alpha: fade in/out (same as _drawtext_filter alpha logic)
  const alpha = interpolate(
    localFrame,
    [0, fadeDurFrames, durationFrames - fadeDurFrames, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  let transform = "";
  let extraOpacity = 1;

  switch (animation) {
    case "slide-up": {
      const slideY = spring({
        frame: localFrame,
        fps,
        config: { damping: 12, stiffness: 100 },
      });
      transform = `translateY(${interpolate(slideY, [0, 1], [60, 0])}px)`;
      break;
    }
    case "typewriter":
      // Handled via text truncation below
      break;
    case "scale-in": {
      const scaleVal = spring({
        frame: localFrame,
        fps,
        config: { damping: 10, stiffness: 80 },
      });
      const s = interpolate(scaleVal, [0, 1], [0.5, 1]);
      transform = `scale(${s})`;
      break;
    }
    case "fade":
    default:
      break;
  }

  // Typewriter: reveal characters over first 60% of duration
  let displayText = text;
  if (animation === "typewriter") {
    const revealFrames = Math.round(durationFrames * 0.6);
    const charsToShow = Math.min(
      text.length,
      Math.round(interpolate(localFrame, [0, revealFrames], [0, text.length], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }))
    );
    displayText = text.slice(0, charsToShow);
  }

  return (
    <div
      style={{
        position: "absolute",
        bottom: 120,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity: alpha * extraOpacity,
        transform,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.5)",
          padding: "12px 24px",
          borderRadius: 8,
          maxWidth: "85%",
        }}
      >
        <span
          style={{
            color: "#fff",
            fontSize,
            fontFamily: "'Inter', 'Noto Sans', sans-serif",
            fontWeight: 500,
            lineHeight: 1.3,
            textAlign: "center",
            display: "block",
          }}
        >
          {displayText}
        </span>
      </div>
    </div>
  );
};
