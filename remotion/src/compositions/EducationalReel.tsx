import React from "react";
import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { z } from "zod";
import { KenBurnsFrame } from "../components/KenBurnsFrame";
import { ProgressBar } from "../components/ProgressBar";
import { TextOverlay } from "../components/TextOverlay";
import type { EducationalReelProps } from "../types";

export const educationalReelSchema = z.object({
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
  showStepNumbers: z.boolean(),
  showProgressBar: z.boolean(),
});

/**
 * EducationalReel — step-by-step educational format with numbered frames and progress bar.
 */
export const EducationalReel: React.FC<EducationalReelProps> = ({
  frames,
  crossfadeDuration,
  textAnimation,
  fps: propsFps,
  showStepNumbers,
  showProgressBar,
}) => {
  const { fps } = useVideoConfig();
  const effectiveFps = propsFps || fps;
  const crossfadeFrames = Math.round(crossfadeDuration * effectiveFps);

  const segments: Array<{
    startFrame: number;
    durationFrames: number;
    frameData: (typeof frames)[0];
    index: number;
  }> = [];

  let currentStart = 0;
  for (let i = 0; i < frames.length; i++) {
    const durationFrames = Math.round(frames[i].duration * effectiveFps);
    segments.push({
      startFrame: currentStart,
      durationFrames,
      frameData: frames[i],
      index: i,
    });
    currentStart += durationFrames - crossfadeFrames;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {segments.map((seg, i) => {
        const overlayText = showStepNumbers
          ? `${seg.index + 1}/${frames.length}. ${seg.frameData.overlayText}`
          : seg.frameData.overlayText;

        return (
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
              {overlayText && (
                <TextOverlay
                  text={overlayText}
                  animation={textAnimation}
                  startFrame={0}
                  durationFrames={seg.durationFrames}
                  fontSize={48}
                />
              )}
            </AbsoluteFill>
          </Sequence>
        );
      })}
      {showProgressBar && <ProgressBar />}
    </AbsoluteFill>
  );
};
