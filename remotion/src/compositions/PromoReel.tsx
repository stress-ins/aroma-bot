import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";
import { BrandWatermark } from "../components/BrandWatermark";
import { KenBurnsFrame } from "../components/KenBurnsFrame";
import { TextOverlay } from "../components/TextOverlay";
import type { PromoReelProps } from "../types";

export const promoReelSchema = z.object({
  frames: z.array(
    z.object({
      imagePath: z.string(),
      duration: z.number(),
      overlayText: z.string(),
      motionType: z.number(),
    })
  ),
  crossfadeDuration: z.number(),
  textAnimation: z.enum(["fade", "slide-up", "typewriter", "scale-in"]),
  fps: z.number(),
  brandColor: z.string(),
  ctaText: z.string(),
  watermarkPath: z.string().optional(),
});

const CtaButton: React.FC<{ text: string; color: string }> = ({
  text,
  color,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 8, stiffness: 80 } });
  const s = interpolate(scale, [0, 1], [0.3, 1]);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 200,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        transform: `scale(${s})`,
      }}
    >
      <div
        style={{
          backgroundColor: color,
          padding: "20px 60px",
          borderRadius: 40,
          boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
        }}
      >
        <span
          style={{
            color: "#fff",
            fontSize: 36,
            fontFamily: "'Inter', 'Noto Sans', sans-serif",
            fontWeight: 700,
          }}
        >
          {text}
        </span>
      </div>
    </div>
  );
};

/**
 * PromoReel — brand-focused promo template with CTA button on last frame and watermark.
 */
export const PromoReel: React.FC<PromoReelProps> = ({
  frames,
  crossfadeDuration,
  textAnimation,
  fps: propsFps,
  brandColor,
  ctaText,
}) => {
  const { fps } = useVideoConfig();
  const effectiveFps = propsFps || fps;
  const crossfadeFrames = Math.round(crossfadeDuration * effectiveFps);

  const segments: Array<{
    startFrame: number;
    durationFrames: number;
    frameData: (typeof frames)[0];
    isLast: boolean;
  }> = [];

  let currentStart = 0;
  for (let i = 0; i < frames.length; i++) {
    const durationFrames = Math.round(frames[i].duration * effectiveFps);
    segments.push({
      startFrame: currentStart,
      durationFrames,
      frameData: frames[i],
      isLast: i === frames.length - 1,
    });
    currentStart += durationFrames - crossfadeFrames;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {segments.map((seg, i) => (
        <Sequence
          key={i}
          from={seg.startFrame}
          durationInFrames={seg.durationFrames}
        >
          <AbsoluteFill>
            <KenBurnsFrame
              imagePath={seg.frameData.imagePath}
              motionType={seg.frameData.motionType}
              startFrame={0}
              durationFrames={seg.durationFrames}
            />
            {seg.frameData.overlayText && (
              <TextOverlay
                text={seg.frameData.overlayText}
                animation={textAnimation}
                startFrame={0}
                durationFrames={seg.durationFrames}
              />
            )}
            {seg.isLast && ctaText && (
              <CtaButton text={ctaText} color={brandColor} />
            )}
          </AbsoluteFill>
        </Sequence>
      ))}
      <BrandWatermark />
    </AbsoluteFill>
  );
};
