import React from "react";
import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { z } from "zod";
import { KenBurnsFrame } from "../components/KenBurnsFrame";
import { TextOverlay } from "../components/TextOverlay";
import type { AromaReelProps } from "../types";

export const aromaReelSchema = z.object({
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
});

/**
 * AromaReel — primary composition replicating FFmpeg Ken Burns + crossfade + text overlays.
 *
 * Each frame gets a Ken Burns animation (4 alternating patterns matching _kb_filter()),
 * crossfade transitions between frames, and text overlays with configurable animation.
 */
export const AromaReel: React.FC<AromaReelProps> = ({
  frames,
  crossfadeDuration,
  textAnimation,
  fps: propsFps,
}) => {
  const { fps } = useVideoConfig();
  const effectiveFps = propsFps || fps;
  const crossfadeFrames = Math.round(crossfadeDuration * effectiveFps);

  // Calculate start frame for each segment
  const segments: Array<{
    startFrame: number;
    durationFrames: number;
    frameData: (typeof frames)[0];
  }> = [];

  let currentStart = 0;
  for (let i = 0; i < frames.length; i++) {
    const durationFrames = Math.round(frames[i].duration * effectiveFps);
    segments.push({
      startFrame: currentStart,
      durationFrames,
      frameData: frames[i],
    });
    // Next frame starts crossfadeDuration before this one ends
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
          </AbsoluteFill>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
